import os
from typing import Any, cast
import pandas as pd
from modules.structured_logger import SovereignLogger
from modules.hybrid_scoring import predict_and_explain, train_hybrid_model, FEATURES

logger = SovereignLogger("sovereign.ranker")

class LightGBMRanker:
    """
    Adapter class that maps the old LightGBMRanker interface to the consolidated
    XGBoost Meta-Model (HybridScorer) to ensure a single, consistent ML pipeline.
    """

    def __init__(self, model_path=None):
        self.model_path = model_path
        # Model is loaded lazily inside predict_and_explain
        pass

    def rank_stocks(self, stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Ranks a list of stocks using the unified XGBoost model from hybrid_scoring.
        """
        if not stocks:
            return []

        df = pd.DataFrame(stocks)
        
        # Predict score for each stock
        ml_scores = []
        for stock in stocks:
            pred_score, _ = predict_and_explain(stock)
            # if predict_and_explain fails, it returns (0.0, {})
            ml_scores.append(pred_score)
            
        df["ml_rank_score"] = ml_scores
        
        # If all scores are 0 (e.g. model not trained), fallback to heuristic
        if (df["ml_rank_score"] == 0.0).all():
            self._apply_heuristic_ranking(df)

        df = df.sort_values(by="ml_rank_score", ascending=False)
        return cast(list[dict[str, Any]], df.to_dict("records"))

    def _apply_heuristic_ranking(self, df: pd.DataFrame):
        """
        Fallback heuristic ranking using the 13-feature metrics where possible.
        """
        # Ensure fallback columns exist
        for col in ["score", "Ret_6M", "Ret_3M", "Vol_Breakout", "Dist_From_52W_High"]:
            if col not in df.columns:
                df[col] = 0.0

        fundamental_norm = df["score"] / 100.0
        momentum_norm = df["Ret_6M"] * 0.6 + df["Ret_3M"] * 0.4
        import numpy as np
        vol_norm = np.clip(df["Vol_Breakout"], 0, 3) / 3.0
        dist_norm = 1.0 - np.clip(df["Dist_From_52W_High"], 0, 1)

        df["ml_rank_score"] = (
            fundamental_norm * 0.40 + momentum_norm * 0.30 + vol_norm * 0.15 + dist_norm * 0.15
        )

    def train(self, data: pd.DataFrame = None, target_col: str = "forward_return"):
        """
        Delegates training to hybrid_scoring.py's consolidated XGBoost model.
        """
        logger.info("Delegating ranker training to consolidated Hybrid Scorer (XGBoost)...")
        # hybrid_scoring trains directly from DB, ignoring passed DataFrame
        return train_hybrid_model()

if __name__ == "__main__":
    ranker = LightGBMRanker()
    logger.info("Ranker (XGBoost Adapter) initialized.")
