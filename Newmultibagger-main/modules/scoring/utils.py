"""
Scoring utilities: safe conversions, IC metrics, Sharpe calculations.

Extracted from modules/hybrid_scoring.py.
"""

from typing import Any
import numpy as np
import pandas as pd


def safe_float(value: Any, default: float = 0.0) -> float:
    """Convert any value to float safely, returning default on failure."""
    if value is None:
        return default
    try:
        v = float(value)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _finite_or_none(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _spearman_ic(y_true: pd.Series, y_pred: pd.Series) -> float | None:
    """Return Spearman rank correlation, or None when <2 valid pairs."""
    valid = y_true.notna() & y_pred.notna()
    yt, yp = y_true[valid], y_pred[valid]
    if len(yt) < 2:
        return None
    return _finite_or_none(yt.corr(yp, method="spearman"))


def _top_quantile_sharpe(
    returns: pd.Series,
    quantile: float = 0.2,
    periods_per_year: int = 4,
) -> float | None:
    """Annualised Sharpe on the top-quantile (long-only) return slice."""
    if returns.empty:
        return None
    n = max(1, int(len(returns) * quantile))
    top = returns.nlargest(n)
    if top.std() == 0 or len(top) < 2:
        return None
    return _finite_or_none(top.mean() / top.std() * np.sqrt(periods_per_year))
