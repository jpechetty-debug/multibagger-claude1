"""
research/feature_stability.py

Measures factor drift between the training window and holdout window.
Outputs JSON payload to validation/feature_stability.json indicating which features have drifted.
"""

import os
import json
import numpy as np
import pandas as pd
import polars as pl
from pathlib import Path
from scipy.stats import ks_2samp

from core.observability.logger import get_logger
from modules.data_layer.parquet.lake_manager import ParquetLakeManager
from modules.scoring.ml_score import FEATURES, _sanitize_features
from research.validation_contract import ValidationResult
from research.validation_registry import ValidationRegistry

logger = get_logger("research.feature_stability")
VALIDATION_DIR = Path(__file__).resolve().parents[1] / "validation"

from research.dataset_utils import load_evaluation_dataset

def load_period_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Load data for a specific period."""
    return load_evaluation_dataset(start_date, end_date)

def run_feature_stability() -> dict:
    logger.info("Starting feature stability audit (KS-Test)")
    
    # Define our standard windows
    train_start, train_end = "2010-01-01", "2017-12-31"
    holdout_start, holdout_end = "2018-01-01", "2020-12-31"
    
    train_df = load_period_data(train_start, train_end)
    holdout_df = load_period_data(holdout_start, holdout_end)
    
    if train_df.empty or holdout_df.empty:
        logger.warning("Missing data for stability audit.")
        return {}
        
    available_features = [f for f in FEATURES if f in train_df.columns and f in holdout_df.columns]
    
    X_train = _sanitize_features(train_df[available_features])
    X_holdout = _sanitize_features(holdout_df[available_features])
    
    drift_metrics = {}
    drift_alerts = []
    
    for feature in available_features:
        # We sample if the datasets are huge to speed up KS-Test
        f_train = X_train[feature].dropna()
        f_holdout = X_holdout[feature].dropna()
        
        if len(f_train) > 10000:
            f_train = f_train.sample(10000, random_state=42)
        if len(f_holdout) > 10000:
            f_holdout = f_holdout.sample(10000, random_state=42)
            
        if len(f_train) > 0 and len(f_holdout) > 0:
            # KS-test for distribution shift
            stat, p_value = ks_2samp(f_train, f_holdout)
            
            # Simple difference in means
            train_mean = f_train.mean()
            holdout_mean = f_holdout.mean()
            shift_pct = abs((holdout_mean - train_mean) / train_mean) if train_mean != 0 else 0.0
            
            # Record metrics
            drift_metrics[feature] = {
                "ks_statistic": float(stat),
                "p_value": float(p_value),
                "mean_shift_pct": float(shift_pct)
            }
            
            # Alert threshold (e.g. p < 0.01 and shift > 20%)
            if p_value < 0.01 and shift_pct > 0.20:
                drift_alerts.append(feature)
                
    passed = len(drift_alerts) == 0
    
    metrics = {
        "drifted_features": drift_alerts,
        "feature_metrics": drift_metrics
    }
    
    registry = ValidationRegistry()
    run_id = registry.register_run(
        model_version="xgboost_meta_v1",
        training_window=f"{train_start}_{train_end}",
        holdout_window=f"{holdout_start}_{holdout_end}",
        feature_set="extended_features",
        hyperparameters={}
    )
    
    res = ValidationResult(
        run_id=run_id,
        model_version="xgboost_meta_v1",
        validation_type="Feature Stability Audit",
        passed=passed,
        metrics=metrics
    )
    
    out_file = VALIDATION_DIR / "feature_stability.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(res.to_dict(), indent=4))
    
    logger.info(f"Feature stability audit completed. Drifted features: {len(drift_alerts)}. Saved to validation/feature_stability.json")
    return res.to_dict()

if __name__ == "__main__":
    result = run_feature_stability()
    print("Feature Stability Audit complete. Check validation/feature_stability.json")
