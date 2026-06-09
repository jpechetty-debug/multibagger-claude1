# worker/celery_app.py — BEAT SCHEDULE PATCH
#
# Problem
# -------
# worker/tasks.py defines two ML tasks:
#   - retrain_xgboost      → full pipeline retraining
#   - (no batch inference task exists yet — see batch_ml_inference below)
#
# Neither is wired into beat_schedule, so:
#   - The model is NEVER automatically retrained after the first manual run
#   - ml_ops.batch_update_multibaggers_ml() is NEVER called, so
#     ml_predicted_return / shap_breakdown / shap_top_drivers in the
#     multibaggers table are always NULL between screener runs
#
# Fix
# ---
# Add two entries to beat_schedule AND add the batch inference Celery task.
#
#
# STEP 1 — In worker/celery_app.py, add these two entries to beat_schedule:
#
#     "ml-retrain-weekly": {
#         "task":     "worker.tasks.retrain_xgboost",
#         "schedule": crontab(hour="2", minute="0", day_of_week="0"),
#         "options":  {"queue": "ml"},
#     },
#     "ml-batch-inference-nightly": {
#         "task":     "worker.tasks.batch_ml_inference",
#         "schedule": crontab(hour="6", minute="30", day_of_week="1-5"),
#         "options":  {"queue": "ml"},
#     },
#
# The full patched beat_schedule block is shown below for reference.
#
#
# STEP 2 — In worker/tasks.py, add the new batch_ml_inference task
#          (see tasks_ml_patch.py).
#
#
# ── Full patched beat_schedule (replace the existing one) ────────────────────

beat_schedule_patch = {
    # ── Market scanning ───────────────────────────────────────────────────────
    "full-market-scan": {
        "task":     "worker.tasks.run_full_scan",
        "schedule": crontab(hour="9", minute="30", day_of_week="1-5"),
        "args":     (),
        "options":  {"queue": "screening"},
    },
    # ── Data maintenance ──────────────────────────────────────────────────────
    "pit-retention-prune": {
        "task":     "worker.tasks.prune_pit_data",
        "schedule": crontab(hour="1", minute="0", day_of_week="0"),
        "options":  {"queue": "maintenance"},
    },
    "regime-cache-refresh": {
        "task":     "worker.tasks.refresh_regime_cache",
        "schedule": crontab(minute="*/30"),
        "options":  {"queue": "maintenance"},
    },
    # ── ML model lifecycle ────────────────────────────────────────────────────
    #
    # Weekly retrain — every Sunday at 02:00 IST.
    # check_retraining_trigger() gates the actual work: if fewer than
    # _RETRAIN_THRESHOLD (50) new PIT rows have arrived since last training
    # the function returns False and training is skipped cleanly.
    # Use --force on the CLI to bypass the gate manually.
    "ml-retrain-weekly": {
        "task":     "worker.tasks.retrain_xgboost",
        "schedule": crontab(hour="2", minute="0", day_of_week="0"),
        "options":  {"queue": "ml"},
    },
    #
    # Nightly batch inference — every weekday at 06:30 IST (before market open).
    # Refreshes ml_predicted_return, shap_breakdown, shap_top_drivers for every
    # row in multibaggers using the current trained model.  No-ops gracefully
    # when model_is_trained() is False.
    "ml-batch-inference-nightly": {
        "task":     "worker.tasks.batch_ml_inference",
        "schedule": crontab(hour="6", minute="30", day_of_week="1-5"),
        "options":  {"queue": "ml"},
    },
}

# ── Paste the above keys into the existing app.conf.update(beat_schedule={…})
#    block in worker/celery_app.py — do not replace the whole file.
