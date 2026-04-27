# scripts/train_hybrid_model.py
"""
Sovereign AI — ML Meta-Model Training Entry Point
Reproducibly retrains the XGBoost forward-return predictor.
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.hybrid_scoring import train_hybrid_model
from modules.structured_logger import SovereignLogger

logger = SovereignLogger("sovereign.scripts.train_ml")

def main():
    parser = argparse.ArgumentParser(description="Retrain Sovereign Hybrid XGBoost Model")
    parser.add_argument("--force", action="store_true", help="Force retraining regardless of data size")
    args = parser.parse_args()

    logger.info("Starting ML model retraining cycle")
    
    # Ensure runtime/models exists
    model_dir = PROJECT_ROOT / "runtime" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    success = train_hybrid_model()
    
    if success:
        logger.info("ML model retraining successful", path=str(model_dir / "xgboost_meta_model.pkl"))
    else:
        logger.error("ML model retraining failed or skipped due to insufficient data")
        sys.exit(1)

if __name__ == "__main__":
    main()
