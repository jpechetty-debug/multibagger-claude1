"""
research/compounder_validation.py

Checks if the model actually catches known historical multibaggers.
Calculates the Compounder Capture Rate based on the compounder registry.
Outputs to validation/compounder.json.
"""

import os
import json
import joblib
import pandas as pd
import polars as pl
from pathlib import Path

from core.observability.logger import get_logger
from modules.data_layer.parquet.lake_manager import ParquetLakeManager
from modules.scoring.ml_score import FEATURES, MODEL_PATH, _sanitize_features
from research.compounder_registry import get_compounders, is_compounder_in_window
from research.validation_contract import ValidationResult
from research.validation_registry import ValidationRegistry

logger = get_logger("research.compounder_validation")
VALIDATION_DIR = Path(__file__).resolve().parents[1] / "validation"

from research.dataset_utils import load_evaluation_dataset

def run_compounder_validation() -> dict:
    logger.info("Starting compounder capture validation")
    
    if not os.path.exists(MODEL_PATH):
        logger.error("No trained model found.")
        return {}
        
    df = load_evaluation_dataset()
    if df.empty:
        logger.warning("Evaluation dataset is empty.")
        return {}
        
    model = joblib.load(MODEL_PATH)
    
    available_features = [f for f in FEATURES if f in df.columns]
    
    # We only care about dates that we have full data for
    df = df.dropna(subset=available_features, how="all").copy()
    X = _sanitize_features(df[available_features])
    df["pred_return"] = model.predict(X)
    
    compounders = get_compounders()
    dates = sorted(df['as_of_date'].unique())
    
    capture_metrics = {ticker: {"hits": 0, "total_windows": 0} for ticker in compounders}
    
    for dt in dates:
        dt_df = df[df['as_of_date'] == dt]
        # Top 50 ranked by the model on this date
        top50_symbols = set(dt_df.nlargest(50, 'pred_return')['symbol'].tolist())
        # We strip .NS from symbol if needed, though they are usually matching.
        
        for ticker in compounders:
            if is_compounder_in_window(ticker, dt):
                # We need to know if the ticker existed in the dataset on this date
                # to penalize only if it was actually screenable
                ticker_in_data = any(sym.startswith(ticker) for sym in dt_df["symbol"])
                
                if ticker_in_data:
                    capture_metrics[ticker]["total_windows"] += 1
                    # Check if ticker is in top 50
                    if any(sym.startswith(ticker) for sym in top50_symbols):
                        capture_metrics[ticker]["hits"] += 1

    # Calculate individual and weighted capture rates
    total_cagr_weight = 0.0
    weighted_hits = 0.0
    
    for ticker, stats in capture_metrics.items():
        hits = stats["hits"]
        total = stats["total_windows"]
        
        if total > 0:
            capture_rate = hits / total
            stats["capture_rate"] = float(capture_rate)
        else:
            stats["capture_rate"] = 0.0
            capture_rate = 0.0
            
        cagr = compounders[ticker]["cagr"]
        weight = cagr * total  # Give more weight to higher CAGR and more frequent windows
        
        weighted_hits += capture_rate * weight
        total_cagr_weight += weight
        
    if total_cagr_weight > 0:
        overall_capture_rate = float(weighted_hits / total_cagr_weight)
    else:
        overall_capture_rate = 0.0
        
    passed = bool(overall_capture_rate > 0.60)
    
    metrics = {
        "overall_weighted_capture_rate": overall_capture_rate,
        "compounders": capture_metrics
    }
    
    registry = ValidationRegistry()
    run_id = registry.register_run(
        model_version="xgboost_meta_v1",
        training_window="N/A",
        holdout_window="ALL",
        feature_set="extended_features",
        hyperparameters={}
    )
    
    res = ValidationResult(
        run_id=run_id,
        model_version="xgboost_meta_v1",
        validation_type="Compounder Capture",
        passed=passed,
        metrics=metrics,
    )
    
    out_file = VALIDATION_DIR / "compounder.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(res.to_dict(), indent=4))
    
    logger.info(f"Compounder capture validation completed. Rate: {overall_capture_rate:.2%}. Saved to validation/compounder.json")
    return res.to_dict()

if __name__ == "__main__":
    result = run_compounder_validation()
    print("Compounder Capture Audit complete. Check validation/compounder.json")
