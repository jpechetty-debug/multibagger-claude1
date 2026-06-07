#!/usr/bin/env python
# scripts/train_hybrid_model.py
# Sovereign AI — ML Meta-Model Training Entry Point
# Reproducibly retrains the XGBoost forward-return predictor.
#
# Usage:
#   python scripts/train_hybrid_model.py              # retrain if enough new data
#   python scripts/train_hybrid_model.py --force      # always retrain
#   python scripts/train_hybrid_model.py --dry-run    # show status, do not train
#   python scripts/train_hybrid_model.py --status     # print last training metadata
#   python scripts/train_hybrid_model.py --importance # show feature importances

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.observability.logger import get_logger
    logger = get_logger("sovereign.scripts.train_ml")
except Exception:
    import logging
    logger = logging.getLogger("sovereign.scripts.train_ml")


def _print_json(obj: dict, label: str = "") -> None:
    if label:
        print(f"\n── {label} ──")
    print(json.dumps(obj, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Retrain Sovereign Hybrid XGBoost Meta-Model",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--force",      action="store_true", help="Force retraining regardless of data size")
    parser.add_argument("--dry-run",    action="store_true", help="Print status without training")
    parser.add_argument("--status",     action="store_true", help="Print last training metadata and walk-forward report")
    parser.add_argument("--importance", action="store_true", help="Print feature importances from trained model")
    args = parser.parse_args()

    # ── Ensure runtime/models dir exists ──
    model_dir = PROJECT_ROOT / "runtime" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    from modules.hybrid_scoring import (
        get_feature_importance,
        load_walk_forward_report,
        model_is_trained,
    )
    from modules.ml_ops import (
        check_retraining_trigger,
        get_last_training_info,
        run_automated_training,
    )

    # ── --status ──
    if args.status:
        last = get_last_training_info()
        wf   = load_walk_forward_report()
        _print_json(last, "Last Training Metadata")
        if wf:
            _print_json(wf, "Walk-Forward Report")
        else:
            print("\nNo walk-forward report found.")
        sys.exit(0)

    # ── --importance ──
    if args.importance:
        if not model_is_trained():
            print("Model not trained yet. Run without --importance to train first.")
            sys.exit(1)
        imp = get_feature_importance()
        _print_json(imp, "Feature Importances (gain-normalised)")
        sys.exit(0)

    # ── --dry-run ──
    if args.dry_run:
        trained   = model_is_trained()
        due       = check_retraining_trigger()
        last      = get_last_training_info()
        wf        = load_walk_forward_report()
        print(f"Model trained   : {trained}")
        print(f"Retraining due  : {due}")
        if last:
            print(f"Last trained at : {last.get('trained_at')}")
            print(f"Record count    : {last.get('record_count')}")
            print(f"WF IC           : {last.get('spearman_ic')}")
        if wf and wf.get("status") == "OK":
            print(f"Walk-forward IC : {wf.get('spearman_ic')}")
            print(f"Hit rate        : {wf.get('hit_rate')}")
            print(f"Folds           : {wf.get('folds')}")
        sys.exit(0)

    # ── Check trigger unless --force ──
    if not args.force:
        if not check_retraining_trigger():
            logger.info("Not enough new data to trigger retraining. Use --force to override.")
            sys.exit(0)

    # ── Train ──
    logger.info("Starting ML model retraining cycle…")
    success = run_automated_training()

    if success:
        wf = load_walk_forward_report() or {}
        logger.info(
            "ML model retraining successful",
            path=str(model_dir / "xgboost_meta_model.pkl"),
            spearman_ic=wf.get("spearman_ic"),
            hit_rate=wf.get("hit_rate"),
            folds=wf.get("folds"),
        )
    else:
        logger.error("ML model retraining failed or skipped due to insufficient data")
        sys.exit(1)


if __name__ == "__main__":
    main()
