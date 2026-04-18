from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import pandas as pd
import numpy as np
import json
import os
import csv
import asyncio
import yfinance as yf
from contextlib import asynccontextmanager
from pathlib import Path

import socket
socket.setdefaulttimeout(20.0)

import time
from datetime import datetime
from typing import Any, Callable

import config as _cfg
from modules.runtime_settings import runtime_settings
from modules.structured_logger import SovereignLogger
from fastapi.staticfiles import StaticFiles

from worker.background_jobs import start_weekly_audit_thread
from modules.dependencies import (
    update_prices_background, 
    app_logger, 
    runtime_logger,
    get_connection,
    _run_sqlite_write_with_retry_sync,
    _run_blocking,
    _run_ticker_blocking,
    _run_sqlite_write_with_retry,
    _json_safe_clean,
    manager
)

from app_routes import public_router
from app_routes.stocks import router as stocks_router
from app_routes.analysis import router as analysis_router
from app_routes.regime import router as regime_router
from app_routes.trading import router as trading_router
from app_routes.system import router as system_router

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

    try:
        yield
    finally:
        if bg_task is not None:
            bg_task.cancel()
            try:
                await bg_task
            except asyncio.CancelledError:
                runtime_logger.info("Embedded background price updater stopped")

app = FastAPI(lifespan=lifespan)

# Setup CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cfg.CORS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
app.mount("/static", StaticFiles(directory=str(WEB_UI_DIR)), name="static")

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
        reload=True,
        reload_excludes=["*.db", "*.db-journal", "*.db-wal", "*.log", "*.txt"]
    )



