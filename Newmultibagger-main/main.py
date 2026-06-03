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
from modules.connections import (
    _run_sqlite_write_with_retry_sync,
    get_connection,
)
from modules.auth import get_api_key
from modules.dependencies import update_prices_background
from modules.structured_logger import SovereignLogger

app_logger = SovereignLogger("sovereign.app")
runtime_logger = SovereignLogger("sovereign.runtime")
from modules.rate_limit import RateLimitExceeded, limiter, rate_limit_exceeded_handler
from modules.runtime_settings import runtime_settings
from worker.background_jobs import start_weekly_audit_thread

PROJECT_ROOT = Path(__file__).resolve().parent
WEB_UI_DIR = PROJECT_ROOT / "web-ui"


# Background Task for Periodic Price Updates
@asynccontextmanager
async def lifespan(app: FastAPI):
    bg_task = None
    if runtime_settings.embed_price_updater_in_web:
        runtime_logger.info(
            "Starting embedded background price updater",
            interval_seconds=runtime_settings.price_update_interval_seconds,
            batch_size=runtime_settings.price_update_batch_size,
        )
        bg_task = asyncio.create_task(update_prices_background())
        app.state.background_price_updater_task = bg_task
    else:
        runtime_logger.info(
            "Embedded background price updater disabled",
            standalone_worker="python -m worker.runtime",
        )

    # Start the multi-worker WebSocket Redis Pub/Sub listener
    from modules.dependencies import manager
    pubsub_task = asyncio.create_task(manager.listen_pubsub())

    try:
        yield
    finally:
        pubsub_task.cancel()
        try:
            await pubsub_task
        except asyncio.CancelledError:
            pass

        if bg_task is not None:
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                runtime_logger.info("Embedded background price updater stopped")


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
