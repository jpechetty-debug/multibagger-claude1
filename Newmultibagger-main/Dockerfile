FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info && \
    rm -rf /var/lib/apt/lists/*

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

RUN groupadd -r appuser && useradd -r -g appuser appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 9005

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9005"]
