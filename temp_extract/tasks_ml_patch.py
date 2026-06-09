# worker/tasks.py — ML SECTION ADDITION
#
# Append this task after the existing retrain_xgboost task.
# It is the nightly counterpart: retrain_xgboost updates the model weights;
# batch_ml_inference re-scores every stock in multibaggers with the current
# model and writes back ml_predicted_return / shap_breakdown / shap_top_drivers.
#
# Without this task the three columns are only populated during a full
# screener run (which may only run weekly). The columns would be stale
# or NULL for most of the week, breaking the /api/ml/status endpoint
# and the SHAP waterfall in the frontend.


@app.task(name="worker.tasks.batch_ml_inference", time_limit=600)
@celery_task_timer("batch_ml_inference")
def batch_ml_inference():
    """Re-score every stock in multibaggers with the current XGBoost model.

    Writes ml_predicted_return, shap_breakdown, shap_top_drivers back to DB.
    No-ops gracefully when the model has not been trained yet.
    """
    try:
        from modules.hybrid_scoring import model_is_trained

        if not model_is_trained():
            logger.info(
                "batch_ml_inference.skipped",
                reason="model not trained — run retrain_xgboost first",
            )
            return {"status": "skipped", "reason": "model_not_trained"}

        from modules.data_layer.data_utils import run_coroutine_sync
        from modules.ml_ops import batch_update_multibaggers_ml

        run_coroutine_sync(batch_update_multibaggers_ml())

        logger.info("batch_ml_inference.completed", updated_at=datetime.now().isoformat())
        return {"status": "success", "completed_at": datetime.now().isoformat()}

    except Exception as exc:
        logger.error("batch_ml_inference.failed", error=str(exc))
        return {"status": "error", "message": str(exc)}
