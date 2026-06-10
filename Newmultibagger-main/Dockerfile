FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# ── Runtime directories ───────────────────────────────────────────────────────
# runtime/models/ is git-ignored (models are large binary artifacts).
# Create it here so model_is_trained() never fails with FileNotFoundError
# and bootstrap has somewhere to write xgboost_meta_model.pkl.
RUN mkdir -p runtime/models runtime/reports runtime/cache

# ── ML cold-start bootstrap ───────────────────────────────────────────────────
# Train a lightweight proxy model on whatever data is available at build time.
# This means every container image ships with a working model — the screener
# never silently falls back to rule-based scoring from the very first request.
# The model will be replaced automatically by the weekly Celery retrain once
# real PIT data accumulates (POST /api/ml/train --force or beat schedule).
#
# Exit 0 is forced because bootstrap may legitimately have no data yet
# (e.g. a fresh image with an empty DB) — we never want a missing model
# to fail the Docker build. The lifespan bootstrap in main.py is the
# runtime safety net for that case.
RUN python scripts/train_hybrid_model.py --bootstrap || true

EXPOSE 9005

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9005"]
