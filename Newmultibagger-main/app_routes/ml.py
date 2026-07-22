# app_routes/ml.py
"""
ML Model Lifecycle API
======================

Endpoints
---------
GET  /api/ml/status          Model health, last training metadata, WF metrics
POST /api/ml/train           Trigger async retraining via Celery (or inline)
POST /api/ml/inference       Batch re-score all multibaggers with current model
GET  /api/ml/explain/{sym}   SHAP waterfall for a single stock
GET  /api/ml/importance      XGBoost gain-based feature importances
GET  /api/ml/walk-forward    Last walk-forward validation report
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel

from modules.auth import get_api_key
from modules.hybrid_scoring import (
    FEATURES,
    get_feature_importance,
    load_walk_forward_report,
    model_is_trained,
    predict_and_explain,
)
from modules.ml_ops import (
    batch_update_multibaggers_ml,
    check_retraining_trigger,
    get_last_training_info,
    ml_status,
)
from core.observability.logger import get_logger

_log = get_logger("sovereign.ml_api")

router = APIRouter(prefix="/api/ml", tags=["ml"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class TrainRequest(BaseModel):
    force: bool = False   # bypass check_retraining_trigger gate


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_ml_status(_: str = Depends(get_api_key)):
    """Full model health snapshot.

    Returns:
        model_trained, model_path, last_training (metadata row),
        walk_forward (last WF report), feature_importance,
        retrain_due (bool — True when ≥50 new PIT rows since last run).
    """
    return ml_status()


@router.post("/train", status_code=status.HTTP_202_ACCEPTED)
async def trigger_training(
    body: TrainRequest,
    _: str = Depends(get_api_key),
):
    """Trigger a full ML retraining cycle.

    Tries Celery first (non-blocking); falls back to inline synchronous
    training when no Celery worker is reachable.

    With ``force=false`` (default) the retraining is skipped when fewer
    than 50 new PIT rows have arrived since the last training run — same
    gate as ``python scripts/train_hybrid_model.py``.

    With ``force=true`` training always runs regardless of row count.
    """
    if not body.force and not check_retraining_trigger():
        return {
            "status": "skipped",
            "reason": "not enough new data (use force=true to override)",
            "last_training": get_last_training_info(),
        }

    # ── Try Celery (async, preferred) ─────────────────────────────────────────
    try:
        from worker.tasks import retrain_xgboost

        task = retrain_xgboost.apply_async(queue="ml")
        _log.info("ML retraining dispatched to Celery", task_id=task.id)
        return {
            "status": "queued",
            "task_id": task.id,
            "mode": "celery",
        }
    except Exception as celery_err:
        _log.warning(
            "Celery unavailable — falling back to inline training",
            error=str(celery_err),
        )

    # ── Inline fallback (blocking — completes before response) ───────────────
    try:
        from modules.ml_ops import run_automated_training

        success = run_automated_training()
        if success:
            wf = load_walk_forward_report() or {}
            return {
                "status": "completed",
                "mode": "inline",
                "spearman_ic": wf.get("spearman_ic"),
                "hit_rate": wf.get("hit_rate"),
                "folds": wf.get("folds"),
            }
        return {
            "status": "skipped",
            "reason": "insufficient PIT data for training",
            "mode": "inline",
        }
    except Exception as exc:
        _log.error("Inline ML training failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Training failed: {exc}",
        ) from exc


@router.post("/inference", status_code=status.HTTP_202_ACCEPTED)
async def trigger_batch_inference(_: str = Depends(get_api_key)):
    """Re-score every stock in multibaggers with the current model.

    Writes ml_predicted_return, shap_breakdown, shap_top_drivers back to DB.
    Queues via Celery when available; runs inline otherwise.
    """
    if not model_is_trained():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model not trained. Call POST /api/ml/train first.",
        )

    # ── Try Celery ────────────────────────────────────────────────────────────
    try:
        from worker.tasks import batch_ml_inference

        task = batch_ml_inference.apply_async(queue="ml")
        return {"status": "queued", "task_id": task.id, "mode": "celery"}
    except Exception as celery_err:
        _log.warning("Celery unavailable — running inference inline", error=str(celery_err))

    # ── Inline fallback ───────────────────────────────────────────────────────
    try:
        await batch_update_multibaggers_ml()
        return {"status": "completed", "mode": "inline"}
    except Exception as exc:
        _log.error("Batch ML inference failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {exc}",
        ) from exc


@router.get("/explain/{symbol}")
async def explain_stock(
    symbol: Annotated[str, Path(min_length=1, max_length=20)],
    _: str = Depends(get_api_key),
):
    """SHAP waterfall breakdown for a single stock.

    Loads the stock's current factor snapshot from multibaggers and runs
    predict_and_explain with all 13 features.

    Returns:
        symbol, ml_prediction (% forward return), shap_values (dict),
        shap_expected_value, top_drivers (list of 5 with direction labels),
        feature_values (the raw inputs that were used).
    """
    if not model_is_trained():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model not trained. Call POST /api/ml/train first.",
        )

    # Load live factor snapshot from DB
    try:
        from modules.data_layer.db_utils import get_db_connection

        with get_db_connection("stocks.db") as conn:
            row = conn.execute(
                """
                SELECT symbol,
                       score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                       debt_equity, cfo_pat_ratio, market_cap_cr,
                       ret_1m, ret_3m, ret_6m,
                       vol_breakout, dist_from_52w_high, roce
                FROM   multibaggers
                WHERE  UPPER(symbol) = UPPER(:sym)
                LIMIT  1
                """,
                {"sym": symbol},
            ).fetchone()
    except Exception as exc:
        _log.error("DB lookup failed in /explain", symbol=symbol, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol}' not found in multibaggers.",
        )

    factors = {f: (row[f] or 0.0) for f in FEATURES}
    result  = predict_and_explain(factors, top_n_drivers=13)   # all features

    return {
        "symbol":               symbol.upper(),
        "ml_prediction":        result.get("ml_prediction"),
        "shap_expected_value":  result.get("shap_expected_value"),
        "shap_values":          result.get("shap_values"),
        "top_drivers":          result.get("top_drivers"),
        "feature_values":       factors,
    }


@router.get("/importance")
async def feature_importance(_: str = Depends(get_api_key)):
    """XGBoost gain-based feature importances (normalised to sum=1).

    Useful for diagnosing which factors the model is relying on most
    and for spotting potential over-fit to a single noisy signal.
    """
    if not model_is_trained():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Model not trained yet.",
        )
    imp = get_feature_importance()
    # Sort by importance descending for readability
    sorted_imp = dict(sorted(imp.items(), key=lambda kv: kv[1], reverse=True))
    return {"feature_importances": sorted_imp}


@router.get("/walk-forward")
async def walk_forward_report(_: str = Depends(get_api_key)):
    """Last persisted walk-forward validation report.

    Fields: status, folds, rows, oos_r2, mae, rmse, spearman_ic,
    hit_rate, top_quantile_sharpe, holdout_rows_excluded, windows
    (per-fold IC, hit_rate, sharpe).

    Returns 404 when training has never been run.
    """
    report = load_walk_forward_report()
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No walk-forward report found. Run POST /api/ml/train first.",
        )
    return report
