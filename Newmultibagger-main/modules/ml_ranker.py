# modules/ml_ranker.py
# Sovereign AI — Stock Ranker: XGBoost Adapter (formerly LightGBM interface)
# Wraps the consolidated hybrid_scoring pipeline with a stable ranking API.

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd

try:
    from core.observability.logger import get_logger
    logger = get_logger("sovereign.ranker")
except Exception:
    import logging
    logger = logging.getLogger("sovereign.ranker")

from modules.hybrid_scoring import (
    FEATURES,
    batch_predict,
    model_is_trained,
    predict_and_explain,
)
from modules.ml_ops import run_automated_training


class LightGBMRanker:
    """Adapter that maps the legacy LightGBMRanker interface to the consolidated
    XGBoost Meta-Model so downstream callers require no changes.

    Usage:
        ranker = LightGBMRanker()
        ranked = ranker.rank_stocks(stocks_list)
    """

    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = model_path   # accepted for API compat; actual path is in hybrid_scoring

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank_stocks(self, stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Rank a list of stock factor dicts by predicted 3-month forward return.

        If the model is trained, uses batch_predict for efficiency.
        Falls back to a transparent heuristic composite if the model is absent.

        Args:
            stocks: Each dict must contain at least 'symbol' plus any subset
                of the 13 factor keys (missing ones default to 0).

        Returns:
            Sorted list (descending ml_rank_score) of the same dicts, each
            augmented with 'ml_rank_score', 'shap_values', and 'top_drivers'.
        """
        if not stocks:
            return []

        if model_is_trained():
            results = batch_predict(stocks)
            df = pd.DataFrame(results)
            # ml_prediction is already in %; use it as the ranking key
            df["ml_rank_score"] = pd.to_numeric(df["ml_prediction"], errors="coerce").fillna(0.0)
        else:
            df = pd.DataFrame(stocks)
            logger.warning("XGBoost model not yet trained — applying heuristic ranking.")
            self._apply_heuristic_ranking(df)
            df["shap_values"] = [{}] * len(df)
            df["top_drivers"] = [[]] * len(df)
            df["ml_prediction"] = df["ml_rank_score"]

        df = df.sort_values("ml_rank_score", ascending=False).reset_index(drop=True)
        df["rank"] = range(1, len(df) + 1)
        return cast(list[dict[str, Any]], df.to_dict("records"))

    def rank_single(self, stock: dict[str, Any]) -> dict[str, Any]:
        """Score and explain a single stock. Returns the stock dict augmented with
        ml_prediction, shap_values, shap_expected_value, and top_drivers."""
        result = predict_and_explain(stock)
        return {**stock, **result}

    def train(self, data: pd.DataFrame | None = None, target_col: str = "forward_return") -> bool:
        """Delegate training to the consolidated hybrid_scoring pipeline.

        The ``data`` and ``target_col`` arguments are accepted for interface
        compatibility but ignored — hybrid_scoring reads directly from the DB.
        """
        logger.info("Delegating ranker training to consolidated XGBoost Meta-Model…")
        return run_automated_training()

    # ------------------------------------------------------------------
    # Heuristic fallback
    # ------------------------------------------------------------------

    def _apply_heuristic_ranking(self, df: pd.DataFrame) -> None:
        """Composite score from fundamental + momentum factors when model is absent.

        Weights:  fundamentals 40% | momentum 30% | volume breakout 15% | price proximity 15%
        """
        for col in ["score", "ret_6m", "ret_3m", "vol_breakout", "dist_from_52w_high"]:
            if col not in df.columns:
                df[col] = 0.0

        # Normalised sub-scores (each [0, 1])
        fundamental_norm = df["score"].clip(0, 100) / 100.0
        ret_6m_norm      = (df["ret_6m"].clip(-100, 1000) + 100) / 1100.0
        ret_3m_norm      = (df["ret_3m"].clip(-100, 1000) + 100) / 1100.0
        momentum_norm    = ret_6m_norm * 0.6 + ret_3m_norm * 0.4
        vol_norm         = np.clip(df["vol_breakout"], 0, 3) / 3.0
        dist_norm        = 1.0 - np.clip(df["dist_from_52w_high"], 0.0, 1.0)

        df["ml_rank_score"] = (
            fundamental_norm * 0.40
            + momentum_norm  * 0.30
            + vol_norm       * 0.15
            + dist_norm      * 0.15
        )


# ---------------------------------------------------------------------------
# Module-level convenience instance
# ---------------------------------------------------------------------------

_DEFAULT_RANKER: LightGBMRanker | None = None


def get_ranker() -> LightGBMRanker:
    """Return (and lazily create) the module-level ranker singleton."""
    global _DEFAULT_RANKER
    if _DEFAULT_RANKER is None:
        _DEFAULT_RANKER = LightGBMRanker()
    return _DEFAULT_RANKER


if __name__ == "__main__":
    ranker = LightGBMRanker()
    logger.info("Ranker (XGBoost Adapter) initialised.")
