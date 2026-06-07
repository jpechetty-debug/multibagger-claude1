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
