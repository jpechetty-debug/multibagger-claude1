"""
research/regime_validation.py

Analyzes model performance grouped by market regimes.
Ensures we know the model's structural weaknesses during different economic cycles.
"""

import os
import json
import joblib
import numpy as np
import pandas as pd
import polars as pl
from pathlib import Path

from core.observability.logger import get_logger
from modules.data_layer.parquet.lake_manager import ParquetLakeManager
from modules.scoring.ml_score import FEATURES, MODEL_PATH, _sanitize_features
from research.validation_contract import ValidationResult
from research.validation_registry import ValidationRegistry
from research.model_snapshot import ModelSnapshotManager
from research.regime_definitions import get_regime_for_date

logger = get_logger("research.regime_validation")
VALIDATION_DIR = Path(__file__).resolve().parents[1] / "validation"

from research.dataset_utils import load_evaluation_dataset

def run_regime_validation() -> dict:
    logger.info("Starting regime-based validation")
    
    if not os.path.exists(MODEL_PATH):
        logger.error("No trained model found.")
        return {}
        
    df = load_evaluation_dataset()
    if df.empty:
        logger.warning("Evaluation dataset is empty.")
        return {}
        
    model = joblib.load(MODEL_PATH)
    
    available_features = [f for f in FEATURES if f in df.columns]
    X = _sanitize_features(df[available_features])
    df["pred_return"] = model.predict(X)
    
    # Map dates to regimes
    df["regime"] = df["as_of_date"].astype(str).apply(get_regime_for_date)
    
    metrics_per_regime = {}
    
    for regime in df["regime"].unique():
        regime_df = df[df["regime"] == regime].copy()
        
        # Hit rate
        y_true = regime_df["forward_return"].values
        y_pred = regime_df["pred_return"].values
        hit_rate = float(((y_true > 0) == (y_pred > 0)).mean())
        
        # Sortino and Alpha logic: top 20 vs benchmark
        dates = sorted(regime_df['as_of_date'].unique())
        top20_returns = []
        benchmark_returns = []
        
        for dt in dates:
            dt_df = regime_df[regime_df['as_of_date'] == dt]
            benchmark_returns.append(dt_df['forward_return'].mean())
            top20 = dt_df.nlargest(20, 'pred_return')
            if not top20.empty:
                top20_returns.append(top20['forward_return'].mean())
            else:
                top20_returns.append(0.0)
                
        # Simple calculations per regime slice (ignoring compounding across disjoint periods)
        # Average return
        avg_top20 = np.mean(top20_returns) if top20_returns else 0.0
        avg_bench = np.mean(benchmark_returns) if benchmark_returns else 0.0
        alpha = float(avg_top20 - avg_bench)
        
        # Max Drawdown estimation on continuous stretches within regime is tough if dates are disjoint.
        # We will compute a simple period-by-period drawdown array and take the worst.
        if top20_returns:
            cum_arr = np.cumprod(1 + np.array(top20_returns))
            running_max = np.maximum.accumulate(cum_arr)
            drawdowns = (cum_arr - running_max) / running_max
            max_dd = float(drawdowns.min()) if len(drawdowns) > 0 else 0.0
        else:
            max_dd = 0.0
            
        metrics_per_regime[regime] = {
            "hit_rate": hit_rate,
            "alpha": alpha,
            "max_drawdown": max_dd
        }
    
    passed = True  # Can add strict threshold logic later
    
    registry = ValidationRegistry()
    run_id = registry.register_run(
        model_version="xgboost_meta_v1",
        training_window="N/A",
        holdout_window="ALL_AVAILABLE",
        feature_set="extended_features",
        hyperparameters={}
    )
    
    res = ValidationResult(
        run_id=run_id,
        model_version="xgboost_meta_v1",
        validation_type="Regime Validation",
        passed=passed,
        metrics=metrics_per_regime,
    )
    
    out_file = VALIDATION_DIR / "regime.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(res.to_dict(), indent=4))
    
    logger.info(f"Regime validation completed. Saved to validation/regime.json")
    return res.to_dict()

if __name__ == "__main__":
    result = run_regime_validation()
    print(json.dumps(result, indent=2))
