#!/usr/bin/env python
# scripts/train_hybrid_model.py
# Sovereign AI — ML Meta-Model Training Entry Point
# Reproducibly retrains the XGBoost forward-return predictor.
#
# Usage:
#   python scripts/train_hybrid_model.py              # retrain if enough new data
#   python scripts/train_hybrid_model.py --force      # always retrain (full PIT pipeline)
#   python scripts/train_hybrid_model.py --bootstrap  # cold-start: train on multibaggers proxy
#   python scripts/train_hybrid_model.py --validate   # re-run WF validation only (no refit)
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
        epilog="""
Examples
--------
  First-time setup (no PIT data yet):
    python scripts/train_hybrid_model.py --bootstrap

  Normal weekly retrain (triggered automatically by Celery beat):
    python scripts/train_hybrid_model.py --force

  Check what would happen without running:
    python scripts/train_hybrid_model.py --dry-run

  Inspect current model metrics:
    python scripts/train_hybrid_model.py --status
    python scripts/train_hybrid_model.py --importance
        """,
    )
    parser.add_argument("--force",      action="store_true", help="Force retraining regardless of data size")
    parser.add_argument("--bootstrap",  action="store_true", help="Cold-start: train on multibaggers proxy target (use when PIT data is empty)")
    parser.add_argument("--validate",   action="store_true", help="Re-run walk-forward validation only — no production refit")
    parser.add_argument("--optimize",   action="store_true", help="Run Optuna Bayesian hyperparameter search before training")
    parser.add_argument("--n-trials",   type=int, default=30, help="Number of Optuna trials (default: 30)")
    parser.add_argument("--dry-run",    action="store_true", help="Print status without training")
    parser.add_argument("--status",     action="store_true", help="Print last training metadata and walk-forward report")
    parser.add_argument("--importance", action="store_true", help="Print feature importances from trained model")
    args = parser.parse_args()

    # ── Ensure runtime/models dir exists ──────────────────────────────────────
    model_dir = PROJECT_ROOT / "runtime" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)

    from modules.hybrid_scoring import (
        bootstrap_synthetic_model,
        get_feature_importance,
        load_walk_forward_report,
        model_is_trained,
        walk_forward_validate,
    )
    from modules.ml_ops import (
        check_retraining_trigger,
        get_last_training_info,
        initialize_ml_metadata,
        run_automated_training,
    )

    initialize_ml_metadata()

    # ── --status ──────────────────────────────────────────────────────────────
    if args.status:
        last = get_last_training_info()
        wf   = load_walk_forward_report()
        _print_json(last or {}, "Last Training Metadata")
        if wf:
            _print_json(wf, "Walk-Forward Report")
        else:
            print("\nNo walk-forward report found — model has never been trained.")
        sys.exit(0)

    # ── --importance ──────────────────────────────────────────────────────────
    if args.importance:
        if not model_is_trained():
            print("Model not trained yet.")
            print("Run: python scripts/train_hybrid_model.py --bootstrap")
            sys.exit(1)
        imp = get_feature_importance()
        _print_json(imp, "Feature Importances (gain-normalised)")
        sys.exit(0)

    # ── --dry-run ─────────────────────────────────────────────────────────────
    if args.dry_run:
        trained = model_is_trained()
        due     = check_retraining_trigger()
        last    = get_last_training_info()
        wf      = load_walk_forward_report()
        print(f"Model trained      : {trained}")
        print(f"Retraining due     : {due}")
        if trained:
            wf_status = (wf or {}).get("status", "unknown")
            print(f"WF report status   : {wf_status}")
        if last:
            print(f"Last trained at    : {last.get('trained_at')}")
            print(f"Record count       : {last.get('record_count')}")
            print(f"WF IC              : {last.get('spearman_ic')}")
        if not trained:
            print("\n⚠  No model file found.")
            print("   Quick start (cold-start):  python scripts/train_hybrid_model.py --bootstrap")
            print("   Full PIT training:         python scripts/train_hybrid_model.py --force")
        sys.exit(0)

    # ── --bootstrap ───────────────────────────────────────────────────────────
    if args.bootstrap:
        logger.info("Bootstrap mode: training on multibaggers proxy target…")
        ok = bootstrap_synthetic_model()
        if ok:
            print("✓ Bootstrap model saved to runtime/models/xgboost_meta_model.pkl")
            print("  This is a proxy model — replace it via --force when PIT data is available.")
        else:
            print("✗ Bootstrap failed — check that multibaggers table has ≥ 20 rows.")
            sys.exit(1)
        sys.exit(0)

    # ── --validate ────────────────────────────────────────────────────────────
    if args.validate:
        if not model_is_trained():
            print("No model found. Run --bootstrap or --force first.")
            sys.exit(1)

        import pandas as pd
        from modules.data_layer.db_utils import get_db_connection

        try:
            with get_db_connection("stocks.db") as conn:
                df = pd.read_sql(
                    """
                    SELECT symbol, as_of_date, price AS pit_price,
                           score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                           debt_equity, cfo_pat_ratio, market_cap_cr,
                           ret_1m, ret_3m, ret_6m,
                           vol_breakout, dist_from_52w_high, roce
                    FROM fundamentals_pit
                    """,
                    conn,
                )
        except Exception as exc:
            print(f"Could not load PIT data: {exc}")
            sys.exit(1)

        if df.empty:
            print("No PIT data available — cannot validate.")
            sys.exit(1)

        # Use score proxy as forward_return for validation (same as bootstrap)
        df["forward_return"] = (
            (df["score"] - df["score"].min())
            / max(df["score"].max() - df["score"].min(), 1.0)
        ) - 0.5

        report = walk_forward_validate(df)
        _print_json(report, "Walk-Forward Validation Report")
        sys.exit(0)

    # ── Optuna optimization if requested ──────────────────────────────────────────
    if args.optimize:
        logger.info("Running Optuna hyperparameter optimization…")
        try:
            import pandas as pd
            from modules.data_layer.db_utils import get_db_connection
            from modules.hybrid_scoring import optuna_optimize, _XGB_PARAMS

            with get_db_connection("stocks.db") as conn:
                df = pd.read_sql(
                    """
                    SELECT symbol, as_of_date, price AS pit_price,
                           score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                           debt_equity, cfo_pat_ratio, market_cap_cr,
                           ret_1m, ret_3m, ret_6m,
                           vol_breakout, dist_from_52w_high, roce
                    FROM fundamentals_pit
                    """,
                    conn,
                )

            if df.empty or len(df) < 20:
                print(f"Not enough PIT data for optimization ({len(df)} rows, need 20+).")
                sys.exit(1)

            # Use score proxy as forward_return
            df["forward_return"] = (
                (df["score"] - df["score"].min())
                / max(df["score"].max() - df["score"].min(), 1.0)
            ) - 0.5

            best_params = optuna_optimize(
                df, n_trials=args.n_trials, cv_folds=3, timeout_seconds=600
            )

            # Save optimized params
            params_path = model_dir / "optuna_best_params.json"
            with open(params_path, "w") as fh:
                json.dump(best_params, fh, indent=2)
            print(f"\u2713 Best params saved to {params_path}")
            _print_json(best_params, "Optuna Best Parameters")

        except Exception as exc:
            print(f"Optuna optimization failed: {exc}")
            sys.exit(1)
        sys.exit(0)

    # ── Check trigger unless --force ────────────────────────────────────────────
    if not args.force:
        if not check_retraining_trigger():
            logger.info(
                "Not enough new PIT data to retrain. Use --force to override, "
                "or --bootstrap for a quick proxy model."
            )
            sys.exit(0)

    # ── Full train ────────────────────────────────────────────────────────────
    logger.info("Starting ML model retraining cycle…")
    success = run_automated_training()

    if success:
        wf = load_walk_forward_report() or {}
        logger.info(
            "ML retraining successful",
            path=str(model_dir / "xgboost_meta_model.pkl"),
            spearman_ic=wf.get("spearman_ic"),
            hit_rate=wf.get("hit_rate"),
            folds=wf.get("folds"),
            wf_status=wf.get("status"),
        )
        print(f"[OK] Model saved to {model_dir / 'xgboost_meta_model.pkl'}")
        if wf.get("status") == "BOOTSTRAP":
            print("  ⚠  Bootstrap model (proxy target) — will improve as PIT data accumulates.")
        elif wf.get("status") == "OK":
            print(f"  WF IC={wf.get('spearman_ic'):.4f}  hit_rate={wf.get('hit_rate'):.4f}  folds={wf.get('folds')}")
    else:
        logger.error("ML retraining failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
