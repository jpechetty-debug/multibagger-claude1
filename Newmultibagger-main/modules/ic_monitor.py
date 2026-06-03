"""
Regime-Conditional IC Monitor
-----------------------------
Computes Information Coefficient per market regime and classifies
signal confidence.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_ic_by_regime(
    predictions_df: pd.DataFrame,
    regime_series: pd.Series,
    pred_col: str = "prediction",
    actual_col: str = "forward_return",
) -> dict[str, dict]:
    """Compute Spearman IC per regime.

    Args:
        predictions_df: Must contain ``pred_col`` and ``actual_col``.
        regime_series: Series aligned to ``predictions_df`` index with
            regime labels (e.g. BULLISH, BEARISH, VOLATILE).

    Returns:
        ``{regime: {"ic": float, "n_obs": int, "confidence": str}}``.
    """
    df = predictions_df[[pred_col, actual_col]].copy()
    df["regime"] = regime_series.reindex(df.index)
    df = df.dropna()

    results: dict[str, dict] = {}
    for regime, group in df.groupby("regime"):
        if len(group) < 3:
            results[str(regime)] = {"ic": None, "n_obs": int(len(group)), "confidence": "INSUFFICIENT_DATA"}
            continue

        y_true = pd.to_numeric(group[actual_col], errors="coerce")
        y_pred = pd.to_numeric(group[pred_col], errors="coerce")
        ic = y_true.corr(y_pred, method="spearman")
        ic = float(ic) if np.isfinite(ic) else 0.0

        confidence = _classify_confidence(ic)
        results[str(regime)] = {
            "ic": round(ic, 4),
            "n_obs": int(len(group)),
            "confidence": confidence,
        }

    return results


def _classify_confidence(ic: float) -> str:
    if ic >= 0.10:
        return "HIGH"
    if ic >= 0.05:
        return "MODERATE"
    return "LOW_SIGNAL_CONFIDENCE"
