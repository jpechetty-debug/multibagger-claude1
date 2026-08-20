"""
research/ablation_engine.py

Performs an ablation study by removing feature groups (Momentum, Quality, Value, Growth)
and evaluating how much performance drops.
Outputs to validation/ablation.json.
"""

import os
import json
import numpy as np
import pandas as pd
import polars as pl
from pathlib import Path

from core.observability.logger import get_logger
from modules.data_layer.parquet.lake_manager import ParquetLakeManager
from modules.scoring.ml_score import FEATURES, _sanitize_features, _make_xgb_regressor
from research.validation_contract import ValidationResult
from research.validation_registry import ValidationRegistry
from research.holdout_validation import _calc_stats

logger = get_logger("research.ablation_engine")
VALIDATION_DIR = Path(__file__).resolve().parents[1] / "validation"

ABLATION_GROUPS = {
    "Momentum": ["ret_1m", "ret_3m", "ret_6m", "vol_breakout", "dist_from_52w_high"],
    "Quality": ["avg_roe_5y", "roce", "debt_equity", "cfo_pat_ratio"],
    "Value": ["pe_ratio"],
    "Growth": ["sales_cagr_5y"],
    "Rule_Score": ["score"]
}

from research.dataset_utils import load_evaluation_dataset

def load_data_split() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = load_evaluation_dataset()
    
    train_df = df[(df["as_of_date"] >= "2010-01-01") & (df["as_of_date"] <= "2017-12-31")].copy()
    holdout_df = df[(df["as_of_date"] >= "2018-01-01") & (df["as_of_date"] <= "2020-12-31")].copy()
    
    return train_df, holdout_df

def evaluate_model(model, holdout_df: pd.DataFrame, features: list) -> dict:
    X_holdout = _sanitize_features(holdout_df[features])
    y_pred = model.predict(X_holdout)
    
    eval_df = holdout_df.copy()
    eval_df["pred_return"] = y_pred
    
    dates = sorted(eval_df['as_of_date'].unique())
    top20_returns = []
    
    for dt in dates:
        dt_df = eval_df[eval_df['as_of_date'] == dt]
        top20 = dt_df.nlargest(20, 'pred_return')
        if not top20.empty:
            top20_returns.append(top20['forward_return'].mean())
        else:
            top20_returns.append(0.0)
            
    cagr, max_dd, sharpe, sortino, arr = _calc_stats(top20_returns)
    return {
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": max_dd
    }

def run_ablation_engine() -> dict:
    logger.info("Starting ablation testing")
    
    train_df, holdout_df = load_data_split()
    if train_df.empty or holdout_df.empty:
        logger.warning("Missing data for ablation engine.")
        return {}
        
    y_train = train_df["forward_return"].values
    
    # 1. Baseline
    available_features = [f for f in FEATURES if f in train_df.columns]
    X_train_base = _sanitize_features(train_df[available_features])
    
    logger.info("Training baseline model...")
    base_model = _make_xgb_regressor()
    base_model.fit(X_train_base, y_train)
    
    base_metrics = evaluate_model(base_model, holdout_df, available_features)
    
    ablation_results = {}
    
    # 2. Ablated runs
    for group_name, feats_to_remove in ABLATION_GROUPS.items():
        logger.info(f"Running ablation for group: {group_name}")
        remaining_features = [f for f in available_features if f not in feats_to_remove]
        
        X_train_ablated = _sanitize_features(train_df[remaining_features])
        ablated_model = _make_xgb_regressor()
        ablated_model.fit(X_train_ablated, y_train)
        
        metrics = evaluate_model(ablated_model, holdout_df, remaining_features)
        
        # Calculate impact (Drop in Sharpe / CAGR)
        cagr_drop = float(base_metrics["cagr"] - metrics["cagr"])
        sharpe_drop = float(base_metrics["sharpe"] - metrics["sharpe"])
        
        ablation_results[group_name] = {
            "ablated_cagr": float(metrics["cagr"]),
            "ablated_sharpe": float(metrics["sharpe"]),
            "cagr_impact": cagr_drop,
            "sharpe_impact": sharpe_drop
        }
        
    passed = True
        
    metrics = {
        "baseline": base_metrics,
        "ablation_impact": ablation_results
    }
    
    registry = ValidationRegistry()
    run_id = registry.register_run(
        model_version="xgboost_meta_v1",
        training_window="2010-2017",
        holdout_window="2018-2020",
        feature_set="extended_features",
        hyperparameters={}
    )
    
    res = ValidationResult(
        run_id=run_id,
        model_version="xgboost_meta_v1",
        validation_type="Ablation Engine",
        passed=passed,
        metrics=metrics
    )
    
    out_file = VALIDATION_DIR / "ablation.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(res.to_dict(), indent=4))
    
    logger.info("Ablation testing completed. Saved to validation/ablation.json")
    return res.to_dict()

if __name__ == "__main__":
    result = run_ablation_engine()
    print("Ablation Engine complete. Check validation/ablation.json")
