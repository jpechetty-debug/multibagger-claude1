import re
import os

with open('main.py', 'r', encoding='utf-8') as f:
    text = f.read()

parts = text.split('# API Endpoints')
# The second part contains all endpoints but might contain if __name__ == '__main__':
block = parts[1]

# Exclude the __main__ block
main_block = ''
idx_main = block.find('if __name__ == "__main__":')
if idx_main != -1:
    idx_end_main = block.find('@app', idx_main) 
    if idx_end_main != -1:
        main_block = block[idx_main:idx_end_main]
        block = block[:idx_main] + '\n' + block[idx_end_main:]
    else:
        main_block = block[idx_main:]
        block = block[:idx_main]

# Also grab the websocket if it's before API Endpoints
ws_idx = text.find('@app.websocket')
ws_block = ''
if ws_idx != -1 and ws_idx < len(parts[0]):
    ws_end = text.find('# Allow CORS', ws_idx)
    if ws_end != -1:
        ws_block = text[ws_idx:ws_end]
        parts[0] = parts[0][:ws_idx] + parts[0][ws_end:]

# Replace @app with @router in the extracted blocks
ws_block = ws_block.replace('@app.websocket', '@router.websocket')
api_routes = block.replace('@app.get', '@router.get').replace('@app.post', '@router.post').replace('@app.websocket', '@router.websocket')

api_file = '''from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
import pandas as pd
import numpy as np
import json
import os
import csv
import asyncio
import yfinance as yf
import time
from datetime import datetime
from pydantic import BaseModel, Field

from modules.dependencies import *
from app_routes.contracts import RegimeStatusResponse
from modules.symbol_utils import normalize_symbol
from modules.revisions import analyze_revisions
from modules.drift_monitor import monitor_drift
from modules.allocation_hrp import HRPAllocator

router = APIRouter()

''' + ws_block + '\n' + api_routes

with open('app_routes/api.py', 'w', encoding='utf-8') as f:
    f.write(api_file)

final_main = '''from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
    _run_sqlite_write_with_retry_sync
)

from app_routes import public_router
from app_routes.api import router as api_router

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
app.include_router(api_router)
app.mount("/static", StaticFiles(directory="web-ui"), name="static")

''' + main_block

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(final_main)

print("Done Refactoring!")
