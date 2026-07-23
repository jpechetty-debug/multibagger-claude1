# modules/ic_monitor.py
# Sovereign AI — Regime-Conditional IC Monitor
# Computes Information Coefficient per market regime and detects signal drift.

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# IC helpers
# ---------------------------------------------------------------------------

Confidence = Literal["HIGH", "MODERATE", "LOW_SIGNAL_CONFIDENCE", "INSUFFICIENT_DATA"]


def _classify_confidence(ic: float) -> Confidence:
    if ic >= 0.10:
        return "HIGH"
    if ic >= 0.05:
        return "MODERATE"
    return "LOW_SIGNAL_CONFIDENCE"


# ---------------------------------------------------------------------------
# Regime-conditional IC
# ---------------------------------------------------------------------------

def compute_ic_by_regime(
    predictions_df: pd.DataFrame,
    regime_series: pd.Series,
    pred_col: str = "prediction",
    actual_col: str = "forward_return",
    min_obs: int = 3,
) -> dict[str, dict]:
    """Compute Spearman IC per market regime.

    Args:
        predictions_df: Must contain ``pred_col`` and ``actual_col``.
        regime_series: Series aligned to ``predictions_df`` index with regime
            labels, e.g. "BULLISH" | "BEARISH" | "VOLATILE" | "SIDEWAYS".
        pred_col: Column name for model predictions.
        actual_col: Column name for actual forward returns.
        min_obs: Minimum group size to compute IC (default 3).

    Returns:
        ``{regime: {"ic": float|None, "n_obs": int, "confidence": str,
                    "mean_return": float|None}}``.
    """
    df = predictions_df[[pred_col, actual_col]].copy()
    df["regime"] = regime_series.reindex(df.index)
    df = df.dropna()

    results: dict[str, dict] = {}
    for regime, group in df.groupby("regime"):
        n = int(len(group))
        if n < min_obs:
            results[str(regime)] = {
                "ic": None, "n_obs": n, "confidence": "INSUFFICIENT_DATA",
                "mean_return": None,
            }
            continue

        y_true = pd.to_numeric(group[actual_col], errors="coerce")
        y_pred = pd.to_numeric(group[pred_col],   errors="coerce")
        valid  = y_true.notna() & y_pred.notna()

        ic: float | None = None
        if valid.sum() >= min_obs:
            raw_ic = y_true[valid].corr(y_pred[valid], method="spearman")
            ic = float(raw_ic) if np.isfinite(raw_ic) else None

        results[str(regime)] = {
            "ic":          round(ic, 4) if ic is not None else None,
            "n_obs":       n,
            "confidence":  _classify_confidence(ic) if ic is not None else "INSUFFICIENT_DATA",
            "mean_return": round(float(y_true.mean()), 6) if not y_true.empty else None,
        }

    return results


# ---------------------------------------------------------------------------
# Rolling IC time-series
# ---------------------------------------------------------------------------

def compute_rolling_ic(
    predictions_df: pd.DataFrame,
    date_col: str = "as_of_date",
    pred_col: str = "prediction",
    actual_col: str = "forward_return",
    window_quarters: int = 4,
) -> pd.DataFrame:
    """Compute a rolling Spearman IC over time to detect signal drift.

    Each row in the output represents one quarter; the IC is computed over
    the trailing ``window_quarters`` periods.

    Args:
        predictions_df: Must contain date, prediction, and actual-return columns.
        date_col: Date column (used to assign quarterly periods).
        pred_col: Model prediction column.
        actual_col: Actual forward return column.
        window_quarters: Rolling window size in quarters.

    Returns:
        DataFrame with columns: period, ic, n_obs, confidence.
        Index is the quarter Period.
    """
    df = predictions_df[[date_col, pred_col, actual_col]].copy()
    df[date_col]  = pd.to_datetime(df[date_col], errors="coerce")
    df[pred_col]  = pd.to_numeric(df[pred_col],  errors="coerce")
    df[actual_col] = pd.to_numeric(df[actual_col], errors="coerce")
    df = df.dropna().sort_values(date_col)
    df["period"]  = df[date_col].dt.to_period("Q")

    periods = sorted(df["period"].unique())
    rows: list[dict] = []

    for i, period in enumerate(periods):
        start_idx = max(0, i - window_quarters + 1)
        window_periods = periods[start_idx : i + 1]
        window_df = df[df["period"].isin(window_periods)]

        y_true = window_df[actual_col]
        y_pred = window_df[pred_col]
        valid  = y_true.notna() & y_pred.notna()
        n = int(valid.sum())

        ic: float | None = None
        if n >= 3:
            raw = y_true[valid].corr(y_pred[valid], method="spearman")
            ic  = float(raw) if np.isfinite(raw) else None

        rows.append({
            "period":     str(period),
            "ic":         round(ic, 4) if ic is not None else None,
            "n_obs":      n,
            "confidence": _classify_confidence(ic) if ic is not None else "INSUFFICIENT_DATA",
        })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Drift detection
# ---------------------------------------------------------------------------

def detect_ic_drift(
    rolling_ic_df: pd.DataFrame,
    lookback_periods: int = 4,
    drift_threshold: float = 0.08,
) -> dict:
    """Flag whether recent IC has drifted significantly from historical baseline.

    Args:
        rolling_ic_df: Output of compute_rolling_ic.
        lookback_periods: Number of most-recent periods to consider as 'recent'.
        drift_threshold: IC drop above this is flagged as drift (default 0.08).

    Returns:
        Dict with keys: baseline_ic, recent_ic, drift, drift_detected.
    """
    if rolling_ic_df.empty or "ic" not in rolling_ic_df.columns:
        return {"drift_detected": False, "reason": "no rolling IC data"}

    ics = pd.to_numeric(rolling_ic_df["ic"], errors="coerce").dropna()
    if len(ics) < lookback_periods + 1:
        return {"drift_detected": False, "reason": "insufficient history"}

    baseline_ic = float(ics.iloc[:-lookback_periods].mean())
    recent_ic   = float(ics.iloc[-lookback_periods:].mean())
    drift       = baseline_ic - recent_ic     # positive = IC has fallen

    return {
        "baseline_ic":    round(baseline_ic, 4),
        "recent_ic":      round(recent_ic,   4),
        "drift":          round(drift,        4),
        "drift_detected": drift > drift_threshold,
    }


# ---------------------------------------------------------------------------
# Runtime helpers used by the scoring engine
# ---------------------------------------------------------------------------

import json as _json  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_IC_CACHE_PATH = _Path(__file__).resolve().parents[1] / "runtime" / "regime_ic_cache.json"


# IC below this is treated as a low-confidence signal for every regime when
# only an overall (non-regime-split) IC is available.
_LOW_IC_THRESHOLD = 0.05


def load_regime_ic_cache() -> dict:
    """Load the persisted regime → IC mapping written by the holdout pipeline.

    Returns a dict of the form::

        {
            "BULLISH": {"ic": 0.12, "n": 45, "valid": True},
            "BEARISH": {"ic": 0.03, "n": 12, "valid": False},
            ...
        }

    Backward compatibility — ``worker.tasks.retrain_xgboost`` currently
    writes a flat ``{"ic_by_regime": {"overall": <ic>, "folds": <n>, ...}}``
    payload because per-regime predictions aren't available from the
    walk-forward report. When the cache is in that flat form, this function
    expands it into the per-regime shape above by applying the overall IC
    to every known regime (BULL, BEAR, SIDEWAYS) — so the scoring engine's
    ``low_regime_ic`` check still functions until true regime-split IC is
    computed.

    Returns an empty dict when the cache file does not exist yet (first run
    before the holdout pipeline has completed).
    """
    try:
        if not _IC_CACHE_PATH.exists():
            return {}
        raw = _json.loads(_IC_CACHE_PATH.read_text())
    except Exception:
        return {}

    ic_by_regime = raw.get("ic_by_regime", {})
    if not isinstance(ic_by_regime, dict):
        return {}

    # Already in the per-regime shape (keys are regime labels with dict values
    # containing "ic") — return as-is.
    if ic_by_regime and all(
        isinstance(v, dict) and "ic" in v for v in ic_by_regime.values()
    ):
        return ic_by_regime

    # Flat shape: {"overall": <ic>, "folds": <n>, "note": ...}
    overall_ic = ic_by_regime.get("overall")
    if overall_ic is None:
        return {}
    n_obs = int(ic_by_regime.get("folds", 0))
    entry = {
        "ic": float(overall_ic),
        "n": n_obs,
        "valid": float(overall_ic) >= _LOW_IC_THRESHOLD,
    }
    return dict.fromkeys(("BULL", "BEAR", "SIDEWAYS"), entry)


def get_current_regime() -> str:
    """Return the current market regime label as used by the scoring weights.

    Reads the regime_status from the shared runtime cache file written by the
    regime watcher background task.  Falls back to ``"SIDEWAYS"`` when the
    cache is unavailable so the scoring engine always gets a valid string.
    """
    _runtime_cache = _Path(__file__).resolve().parents[1] / "runtime" / "regime_status.json"
    try:
        if _runtime_cache.exists():
            payload = _json.loads(_runtime_cache.read_text())
            regime = payload.get("regime", "SIDEWAYS")
            return str(regime).upper() if regime else "SIDEWAYS"
    except Exception:
        pass
    return "SIDEWAYS"
