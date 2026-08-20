# modules/holdout.py
# Sovereign AI — Holdout Period Module
# Locks 2018-2020 as a never-trained-on evaluation set for overfitting detection.

from __future__ import annotations

import numpy as np
import pandas as pd

from modules.scoring.ml_score import (
    FEATURES,
    HOLDOUT_END,
    HOLDOUT_START,
    _finite_or_none,
    _sanitize_features,
)

# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------

def split_holdout(
    df: pd.DataFrame,
    start: str = HOLDOUT_START,
    end: str   = HOLDOUT_END,
    date_col: str = "as_of_date",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a DataFrame into (train, holdout) by the locked date range.

    Args:
        df: DataFrame with a date column.
        start: Holdout start date (inclusive), defaults to HOLDOUT_START.
        end:   Holdout end date   (inclusive), defaults to HOLDOUT_END.
        date_col: Name of the datetime column.

    Returns:
        (train_df, holdout_df) — mutually exclusive, covers all rows.
    """
    dates = pd.to_datetime(df[date_col], errors="coerce")
    mask  = dates.between(start, end)
    return df[~mask].copy(), df[mask].copy()


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_holdout(
    model,
    holdout_df: pd.DataFrame,
    features: list[str] | None = None,
    target_col: str = "forward_return",
    periods_per_year: int = 4,
    top_quantile: float = 0.20,
) -> dict:
    """Run the model on holdout data and compute comprehensive OOS metrics.

    Metrics returned:
        status, rows, oos_r2, mae, rmse, spearman_ic, hit_rate,
        holdout_sharpe (Sharpe of top-quantile long-only slice),
        top_quantile_cagr (annualised mean return of top decile).

    Args:
        model: A fitted model with a .predict(X) method.
        holdout_df: Must contain ``target_col`` and the feature columns.
        features: Override FEATURES if needed.
        target_col: Column name for actual forward returns.
        periods_per_year: Used for Sharpe annualisation (4 = quarterly).
        top_quantile: Fraction of stocks taken as 'long' portfolio (default 20%).

    Returns:
        Plain dict (JSON-serialisable).
    """
    features = features or FEATURES

    if holdout_df.empty or target_col not in holdout_df.columns:
        return {"status": "NO_HOLDOUT_DATA"}

    X      = _sanitize_features(holdout_df[features])
    y_true = pd.to_numeric(holdout_df[target_col], errors="coerce")
    valid  = y_true.notna()
    X, y_true = X.loc[valid], y_true.loc[valid]

    if len(y_true) < 2:
        return {"status": "INSUFFICIENT_HOLDOUT_ROWS", "rows": int(len(y_true))}

    y_pred   = pd.Series(model.predict(X), index=y_true.index, dtype=float)
    residual = y_true - y_pred

    ss_res = float(np.square(residual).sum())
    ss_tot = float(np.square(y_true - y_true.mean()).sum())
    oos_r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan

    spearman_ic = y_true.corr(y_pred, method="spearman")
    hit_rate    = float(((y_true > 0) == (y_pred > 0)).mean())

    # ── Top-quantile portfolio metrics ──
    n_top = max(1, int(len(y_pred) * top_quantile))
    top_idx     = y_pred.nlargest(n_top).index
    top_returns = y_true.loc[top_idx]

    holdout_sharpe: float | None = None
    top_quantile_cagr: float | None = None

    if len(top_returns) > 1 and top_returns.std() > 0:
        holdout_sharpe    = float(
            top_returns.mean() / top_returns.std() * np.sqrt(periods_per_year)
        )
    if not top_returns.empty:
        # Approximate CAGR from mean quarterly return
        mean_qtr = float(top_returns.mean())
        top_quantile_cagr = float((1.0 + mean_qtr) ** periods_per_year - 1.0)

    return {
        "status":              "OK",
        "rows":                int(len(y_true)),
        "oos_r2":              _finite_or_none(oos_r2),
        "mae":                 _finite_or_none(np.abs(residual).mean()),
        "rmse":                _finite_or_none(np.sqrt(np.square(residual).mean())),
        "spearman_ic":         _finite_or_none(spearman_ic),
        "hit_rate":            _finite_or_none(hit_rate),
        "holdout_sharpe":      _finite_or_none(holdout_sharpe),
        "top_quantile_cagr":   _finite_or_none(top_quantile_cagr),
    }


# ---------------------------------------------------------------------------
# Overfitting detection
# ---------------------------------------------------------------------------

def compare_performance(
    wf_ic: float | None = None,
    holdout_ic: float | None = None,
    threshold: float = 0.30,
    *,
    wf_sharpe: float | None = None,
    holdout_sharpe: float | None = None,
) -> dict:
    """Accept either IC-based or Sharpe-based kwargs for backward compatibility."""
    if wf_ic is None and wf_sharpe is not None:
        wf_ic = wf_sharpe
    if holdout_ic is None and holdout_sharpe is not None:
        holdout_ic = holdout_sharpe
    if wf_ic is None or holdout_ic is None:
        raise ValueError("Must provide either (wf_ic, holdout_ic) or (wf_sharpe, holdout_sharpe)")
    return _compare_performance_impl(wf_ic, holdout_ic, threshold)


def _compare_performance_impl(
    wf_ic: float,
    holdout_ic: float,
    threshold: float = 0.30,
) -> dict:
    """Flag overfitting when walk-forward vs holdout IC diverge too much.

    A gap > threshold (default 0.30 IC points) signals the model has
    memorised walk-forward data and is unlikely to generalise.

    Args:
        wf_ic:       Mean Spearman IC from walk-forward folds.
        holdout_ic:  Spearman IC on the locked holdout set.
        threshold:   Maximum acceptable IC gap (default 0.30).

    Returns:
        Dict with wf_ic, holdout_ic, ic_gap, overfitting_detected.
    """
    gap = abs(wf_ic - holdout_ic)
    return {
        "wf_ic":               round(wf_ic,       4),
        "holdout_ic":          round(holdout_ic,   4),
        "ic_gap":              round(gap,           4),
        "sharpe_gap":          round(gap,           4),   # alias for wf_sharpe callers
        "overfitting_detected": gap > threshold,
    }
