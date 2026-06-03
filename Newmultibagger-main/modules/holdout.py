"""
Holdout Period Module
---------------------
Locks 2018-2020 as a never-trained-on test set for overfitting detection.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from modules.hybrid_scoring import (
    FEATURES,
    HOLDOUT_END,
    HOLDOUT_START,
    _finite_or_none,
    _make_xgb_regressor,
    _sanitize_features,
)


def split_holdout(
    df: pd.DataFrame,
    start: str = HOLDOUT_START,
    end: str = HOLDOUT_END,
    date_col: str = "as_of_date",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split DataFrame into train and holdout sets by date range."""
    dates = pd.to_datetime(df[date_col], errors="coerce")
    mask = dates.between(start, end)
    return df[~mask].copy(), df[mask].copy()


def evaluate_holdout(
    model,
    holdout_df: pd.DataFrame,
    features: list[str] | None = None,
    target_col: str = "forward_return",
) -> dict:
    """Run prediction on holdout set and compute OOS metrics."""
    features = features or FEATURES
    if holdout_df.empty or target_col not in holdout_df.columns:
        return {"status": "NO_HOLDOUT_DATA"}

    X = _sanitize_features(holdout_df[features])
    y_true = pd.to_numeric(holdout_df[target_col], errors="coerce")
    valid = y_true.notna()
    X = X.loc[valid]
    y_true = y_true.loc[valid]
    if len(y_true) < 2:
        return {"status": "INSUFFICIENT_HOLDOUT_ROWS", "rows": int(len(y_true))}

    y_pred = pd.Series(model.predict(X), index=y_true.index)
    residual = y_true - y_pred
    ss_res = float(np.square(residual).sum())
    ss_tot = float(np.square(y_true - y_true.mean()).sum())
    oos_r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else np.nan
    spearman_ic = y_true.corr(y_pred, method="spearman")
    hit_rate = float(((y_true > 0) == (y_pred > 0)).mean())

    # Sharpe of top-quantile portfolio
    holdout_copy = holdout_df.loc[valid].copy()
    holdout_copy["prediction"] = y_pred.values
    ranked = holdout_copy.sort_values("prediction", ascending=False)
    top_n = max(1, int(len(ranked) * 0.2))
    top_returns = pd.to_numeric(ranked.head(top_n)[target_col], errors="coerce")
    sharpe = 0.0
    if len(top_returns) > 1 and top_returns.std() > 0:
        sharpe = float(top_returns.mean() / top_returns.std() * np.sqrt(4))

    return {
        "status": "OK",
        "rows": int(len(y_true)),
        "oos_r2": _finite_or_none(oos_r2),
        "spearman_ic": _finite_or_none(spearman_ic),
        "hit_rate": _finite_or_none(hit_rate),
        "rmse": _finite_or_none(np.sqrt(np.square(residual).mean())),
        "holdout_sharpe": _finite_or_none(sharpe),
    }


def compare_performance(
    wf_sharpe: float,
    holdout_sharpe: float,
    threshold: float = 0.3,
) -> dict:
    """Compare walk-forward vs holdout Sharpe. Flag overfitting if gap > threshold."""
    gap = abs(wf_sharpe - holdout_sharpe)
    return {
        "wf_sharpe": wf_sharpe,
        "holdout_sharpe": holdout_sharpe,
        "sharpe_gap": round(gap, 4),
        "overfitting_detected": gap > threshold,
    }
