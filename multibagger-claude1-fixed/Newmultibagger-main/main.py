import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import config as _cfg
from app_routes import public_router
from app_routes.analysis import router as analysis_router
from app_routes.freshness import router as freshness_router
from app_routes.regime import router as regime_router
from app_routes.score_report import router as score_report_router
from app_routes.stocks import router as stocks_router
from app_routes.system import router as system_router
from app_routes.trading import router as trading_router
from app_routes.swarm import router as swarm_router
from app_routes.webhooks import router as webhooks_router
from app_routes.ml import router as ml_router
from app_routes.factor_exposure import router as factor_exposure_router
from app_routes.liquidity_sim import router as liquidity_sim_router
from modules.connections import (
    _run_sqlite_write_with_retry_sync,
    get_connection,
)
from modules.auth import get_api_key
from modules.dependencies import update_prices_background
from core.observability.logger import get_logger

app_logger = get_logger("sovereign.app")
runtime_logger = get_logger("sovereign.runtime")
from modules.rate_limit import RateLimitExceeded, limiter, rate_limit_exceeded_handler
from modules.runtime_settings import runtime_settings
from worker.background_jobs import start_weekly_audit_thread

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_UI_DIR = PROJECT_ROOT / "web-ui"


@asynccontextmanager
async def lifespan(app):
    bg_task = None
    from modules.runtime_settings import runtime_settings
    from core.observability.logger import get_logger
    runtime_logger = get_logger("sovereign.runtime")

    if runtime_settings.embed_price_updater_in_web:
        runtime_logger.info(
            "Starting embedded background price updater",
            interval_seconds=runtime_settings.price_update_interval_seconds,
            batch_size=runtime_settings.price_update_batch_size,
        )
        from modules.dependencies import update_prices_background
        bg_task = asyncio.create_task(update_prices_background())
        app.state.background_price_updater_task = bg_task
    else:
        runtime_logger.info(
            "Embedded background price updater disabled",
            standalone_worker="python -m worker.runtime",
        )

    # Skip heavy background tasks in test mode to prevent lifespan interference
    import os as _os
    if _os.getenv("SOVEREIGN_TESTING"):
        try:
            yield
        finally:
            pass
        return

    # ── ML model cold-start bootstrap ─────────────────────────────────────────
    # Ensures xgboost_meta_model.pkl always exists before the first request.
    # Runs in a background thread so it never delays server startup.
    # run_automated_training() tries PIT data first, falls back to bootstrap.
    def _bootstrap_ml_if_needed():
        try:
            from modules.hybrid_scoring import model_is_trained
            if model_is_trained():
                return  # nothing to do — model already on disk
            runtime_logger.info(
                "ML model not found at startup — running bootstrap in background",
                hint="Replace with full model via POST /api/ml/train",
            )
            from modules.ml_ops import run_automated_training
            success = run_automated_training()
            if success:
                from modules.hybrid_scoring import load_walk_forward_report
                wf = load_walk_forward_report() or {}
                runtime_logger.info(
                    "ML startup bootstrap complete",
                    wf_status=wf.get("status"),
                    spearman_ic=wf.get("spearman_ic"),
                )
            else:
                runtime_logger.warning(
                    "ML startup bootstrap failed",
                    hint="Check multibaggers has >= 20 rows, then POST /api/ml/train",
                )
        except Exception as exc:
            runtime_logger.warning("ML startup bootstrap raised an exception", error=str(exc))

    import concurrent.futures
    import os as _os
    if not _os.getenv("SOVEREIGN_TESTING"):
        _ml_boot_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="ml-boot")
        _ml_boot_executor.submit(_bootstrap_ml_if_needed)

    # WebSocket Redis Pub/Sub listener
    from modules.dependencies import manager
    pubsub_task = asyncio.create_task(manager.listen_pubsub())

    # Webhook delivery retry worker
    from modules.webhook_dispatcher import start_retry_worker
    webhook_retry_task = asyncio.create_task(start_retry_worker())

    try:
        yield
    finally:
        # Tear down pub/sub
        pubsub_task.cancel()
        try:
            await pubsub_task
        except asyncio.CancelledError:
            pass

        # Tear down webhook retry worker
        webhook_retry_task.cancel()
        try:
            await webhook_retry_task
        except asyncio.CancelledError:
            pass

        if bg_task is not None:
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                runtime_logger.info("Embedded background price updater stopped")

        from modules.data_layer.data_service import ScreenerRepository
        if getattr(ScreenerRepository, "_neon_pool", None):
            await ScreenerRepository._neon_pool.close()
            ScreenerRepository._neon_pool = None


app = FastAPI(lifespan=lifespan, dependencies=[Depends(get_api_key)])
app.state.limiter = limiter
if RateLimitExceeded is not None and rate_limit_exceeded_handler is not None:
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# Metrics IP Allowlist Middleware
@app.middleware("http")
async def metrics_ip_allowlist_middleware(request, call_next):
    if request.url.path == "/metrics":
        client_host = request.client.host if request.client else None
        allowed_ips = {"127.0.0.1", "::1", "localhost"}
        allowed_env = os.getenv("ALLOWED_METRICS_IPS", "")
        if allowed_env:
            allowed_ips.update(ip.strip() for ip in allowed_env.split(",") if ip.strip())

        if client_host not in allowed_ips:
            from fastapi.responses import PlainTextResponse
            return PlainTextResponse("Forbidden", status_code=403)

    return await call_next(request)

# Prometheus metrics
try:
    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(app)
except ImportError:
    pass

app.include_router(public_router)
app.include_router(stocks_router)
app.include_router(analysis_router)
app.include_router(regime_router)
app.include_router(trading_router)
app.include_router(system_router)
app.include_router(freshness_router)
app.include_router(score_report_router)
app.include_router(swarm_router)
app.include_router(webhooks_router)
app.include_router(ml_router)
app.include_router(factor_exposure_router)
app.include_router(liquidity_sim_router)

static_dir = WEB_UI_DIR / "dist" if (WEB_UI_DIR / "dist").exists() else WEB_UI_DIR
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn

    if runtime_settings.embed_weekly_audit_in_web:
        start_weekly_audit_thread(
            get_connection=get_connection,
            run_sqlite_write_with_retry_sync=_run_sqlite_write_with_retry_sync,
            logger=runtime_logger,
        )
    else:
        runtime_logger.info(
            "Embedded weekly audit loop disabled",
            standalone_worker="python -m worker.runtime",
        )

    app_logger.info(
        "Starting server",
        host="127.0.0.1",
        port=9005,
        embedded_price_updater=runtime_settings.embed_price_updater_in_web,
        embedded_weekly_audit=runtime_settings.embed_weekly_audit_in_web,
    )
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=9005,
        reload=os.getenv("SOVEREIGN_RELOAD", "false").lower() == "true",
        reload_excludes=["*.db", "*.db-journal", "*.db-wal", "*.log", "*.txt"],
    )


# ── Gate 1: Non-blocking async endpoint patterns ───────────────────────────────────

from modules.risk.risk import RiskGovernor as _RiskGovernor
from modules.tracking.tracker import PortfolioTracker as _PortfolioTracker
from database import weekly_audit_loop as _weekly_audit_loop

_risk_governor = _RiskGovernor()
_tracker       = _PortfolioTracker()



@app.get("/api/multibaggers-async")
async def get_multibaggers(api_key: str = Depends(get_api_key)):
    """Non-blocking multibagger list via ScreenerRepository."""
    from modules.data_layer.data_service import fetch_screener_rows
    rows = await fetch_screener_rows(limit=50)
    return {"multibaggers": [r.model_dump() for r in rows]}


@app.get("/api/microcaps-async")
async def get_microcaps(api_key: str = Depends(get_api_key)):
    """Non-blocking microcap list (market_cap_cr < 500)."""
    from modules.data_layer.data_service import fetch_screener_rows
    all_rows = await fetch_screener_rows(limit=500)
    micros = [r.model_dump() for r in all_rows if (r.market_cap_cr or 9999) < 500]
    return {"microcaps": micros[:50]}


