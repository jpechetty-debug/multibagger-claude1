"""Celery application configuration for Sovereign."""

import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

app = Celery("sovereign", broker=REDIS_URL, backend=REDIS_URL)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={
        "worker.tasks.check_factor_data_freshness": {"queue": "maintenance"},
        "worker.tasks.*": {"queue": "default"},
    },
    beat_schedule={
        "factor-freshness-check": {
            "task": "worker.tasks.check_factor_data_freshness",
            "schedule": 86400.0,  # daily
            "options": {"queue": "maintenance"},
        },
    },
)
