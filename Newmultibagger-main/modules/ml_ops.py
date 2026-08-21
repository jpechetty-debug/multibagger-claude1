# modules/ml_ops.py
# Sovereign AI — ML Operations: automated retraining, metadata, and batch inference.

from __future__ import annotations

import json
from typing import Any

import pandas as pd

try:
    from core.observability.logger import get_logger
    logger = get_logger("sovereign.ml_ops")
except Exception:
    import logging
    logger = logging.getLogger("sovereign.ml_ops")

from modules.data_layer.db_utils import get_db_connection  # ← FIXED: was modules.db_utils
from modules.scoring.ml_score import (
    MODEL_PATH,
    batch_predict,
    get_feature_importance,
    train_hybrid_model,
)

ML_METADATA_TABLE  = "ml_metadata"
_RETRAIN_THRESHOLD = 50   # new PIT rows since last run triggers retraining
_BOOTSTRAP_UPGRADE_MIN_PIT_ROWS = 100


# ---------------------------------------------------------------------------
# Metadata table initialisation
# ---------------------------------------------------------------------------

def initialize_ml_metadata() -> None:
    """Create ml_metadata table if it does not exist (idempotent guard)."""
    try:
        with get_db_connection("stocks.db") as conn:
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {ML_METADATA_TABLE} (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    trained_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    record_count INTEGER,
                    r2_score     REAL,
                    spearman_ic  REAL,
                    hit_rate     REAL,
                    oos_r2       REAL,
                    wf_folds     INTEGER,
                    model_path   TEXT
                )
            """)
            conn.commit()
    except Exception as exc:
        logger.error(f"Failed to initialise ML metadata table: {exc}")


# ---------------------------------------------------------------------------
# Metadata read / write
# ---------------------------------------------------------------------------

def get_last_training_info() -> dict[str, Any]:
    """Return the most recent training metadata row, or empty dict."""
    try:
        with get_db_connection("stocks.db") as conn:
            cursor = conn.execute(f"""
                SELECT trained_at, record_count, r2_score,
                       spearman_ic, hit_rate, oos_r2, wf_folds
                FROM {ML_METADATA_TABLE}
                ORDER BY id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                keys = ["trained_at", "record_count", "r2_score",
                        "spearman_ic", "hit_rate", "oos_r2", "wf_folds"]
                return dict(zip(keys, row, strict=False))
    except Exception as exc:
        logger.error(f"Failed to get last training info: {exc}")
    return {}


def record_training_metadata(
    record_count: int,
    r2_score: float,
    model_path: str,
    *,
    spearman_ic: float | None = None,
    hit_rate: float | None = None,
    oos_r2: float | None = None,
    wf_folds: int | None = None,
) -> None:
    """Persist training-run statistics to ml_metadata."""
    initialize_ml_metadata()   # ensure table exists before INSERT
    try:
        with get_db_connection("stocks.db") as conn:
            conn.execute(f"""
                INSERT INTO {ML_METADATA_TABLE}
                    (record_count, r2_score, spearman_ic, hit_rate, oos_r2, wf_folds, model_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (record_count, r2_score, spearman_ic, hit_rate, oos_r2, wf_folds, model_path))
            conn.commit()
    except Exception as exc:
        logger.error(f"Failed to record training metadata: {exc}")


# ---------------------------------------------------------------------------
# Retraining trigger
# ---------------------------------------------------------------------------

def check_retraining_trigger(threshold_new_records: int = _RETRAIN_THRESHOLD) -> bool:
    """Return True when enough new PIT rows have arrived since last training."""
    try:
        with get_db_connection("stocks.db") as conn:
            current_count = int(
                conn.execute("SELECT COUNT(*) FROM fundamentals_pit").fetchone()[0]
            )

        last_count = get_last_training_info().get("record_count", 0) or 0
        diff = current_count - last_count
        logger.info(
            f"ML retraining check: {diff} new rows "
            f"(current={current_count}, last={last_count}, threshold={threshold_new_records})"
        )
        return diff >= threshold_new_records
    except Exception as exc:
        logger.error(f"Failed to check retraining trigger: {exc}")
    return False


def log_bootstrap_upgrade_availability(
    min_pit_rows: int = _BOOTSTRAP_UPGRADE_MIN_PIT_ROWS,
) -> int | None:
    """Log when a bootstrap model can be replaced by PIT-trained ML."""
    try:
        from modules.scoring.ml_score import load_walk_forward_report

        wf = load_walk_forward_report() or {}
        if not wf.get("is_bootstrap"):
            return None

        with get_db_connection("stocks.db") as conn:
            pit_count = int(
                conn.execute("SELECT COUNT(*) FROM fundamentals_pit").fetchone()[0]
            )

        if pit_count >= min_pit_rows:
            logger.info(
                "Bootstrap model detected with sufficient PIT data; attempting full PIT-trained upgrade",
                pit_rows=pit_count,
                min_pit_rows=min_pit_rows,
            )
        return pit_count
    except Exception as exc:
        logger.debug(f"Bootstrap upgrade availability check skipped: {exc}")
    return None


# ---------------------------------------------------------------------------
# Automated training orchestration
# ---------------------------------------------------------------------------

def run_automated_training() -> bool:
    """Execute the full ML training pipeline and record metadata on success.

    Falls back to bootstrap_synthetic_model() when PIT data is insufficient
    so the model file always exists after the first call.
    """
    initialize_ml_metadata()
    logger.info("Starting automated ML retraining…")

    log_bootstrap_upgrade_availability()
    success = train_hybrid_model()

    if not success:
        logger.warning(
            "train_hybrid_model() skipped — insufficient PIT data. "
            "Attempting bootstrap from multibaggers…"
        )
        from modules.scoring.ml_score import bootstrap_synthetic_model
        success = bootstrap_synthetic_model()
        if not success:
            logger.error("Bootstrap also failed — no model produced.")
            return False
        logger.info("Bootstrap model written. Will be replaced by PIT-trained model on next retrain.")

    from modules.scoring.ml_score import load_walk_forward_report

    wf = load_walk_forward_report() or {}
    spearman_ic = wf.get("spearman_ic")
    hit_rate    = wf.get("hit_rate")
    oos_r2      = wf.get("oos_r2")
    wf_folds    = wf.get("folds")

    try:
        with get_db_connection("stocks.db") as conn:
            current_count = int(
                conn.execute("SELECT COUNT(*) FROM fundamentals_pit").fetchone()[0]
            )
    except Exception:
        current_count = 0

    record_training_metadata(
        current_count, 0.0, MODEL_PATH,
        spearman_ic=spearman_ic,
        hit_rate=hit_rate,
        oos_r2=oos_r2,
        wf_folds=wf_folds,
    )
    logger.info(
        "Automated ML training complete",
        records=current_count,
        ic=spearman_ic,
        hit_rate=hit_rate,
        folds=wf_folds,
    )
    return True


# ---------------------------------------------------------------------------
# Batch inference (async-safe wrapper)
# ---------------------------------------------------------------------------

async def batch_update_multibaggers_ml() -> None:
    """Update ml_predicted_return, shap_breakdown, shap_top_drivers for every
    row in multibaggers."""
    logger.info("Batch updating multibaggers with ML predictions…")

    try:
        with get_db_connection("stocks.db") as conn:
            df = pd.read_sql(
                """
                SELECT symbol,
                       score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                       debt_equity, cfo_pat_ratio, market_cap_cr,
                       ret_1m, ret_3m, ret_6m,
                       vol_breakout, dist_from_52w_high, roce
                FROM multibaggers
                """,
                conn,
            )

        if df.empty:
            logger.info("No rows in multibaggers — nothing to update.")
            return

        records = df.to_dict("records")
        results = batch_predict(records)

        updates = [
            (
                r.get("ml_prediction"),
                json.dumps(r.get("shap_values",  {})),
                json.dumps(r.get("top_drivers",  [])),
                r["symbol"],
            )
            for r in results
        ]

        with get_db_connection("stocks.db") as conn:
            conn.executemany(
                """
                UPDATE multibaggers
                SET ml_predicted_return = ?,
                    shap_breakdown      = ?,
                    shap_top_drivers    = ?
                WHERE symbol = ?
                """,
                updates,
            )
            conn.commit()

        filled = sum(1 for u in updates if u[0] is not None)
        logger.info(f"Batch ML predictions updated: {filled}/{len(updates)} stocks.")

    except Exception as exc:
        logger.error(f"Error during batch ML update: {exc}")


# ---------------------------------------------------------------------------
# Health / status endpoint helper
# ---------------------------------------------------------------------------

def ml_status() -> dict[str, Any]:
    """Return a summary dict suitable for the /api/ml/status endpoint."""
    from modules.scoring.ml_score import load_walk_forward_report, model_is_trained

    return {
        "model_trained":     model_is_trained(),
        "model_path":        MODEL_PATH,
        "last_training":     get_last_training_info(),
        "walk_forward":      load_walk_forward_report(),
        "feature_importance":get_feature_importance(),
        "retrain_due":       check_retraining_trigger(),
    }
