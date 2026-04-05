__all__ = ['BLOCKING_IO_CONCURRENCY', 'CACHE_AUDIT_TTL', 'CACHE_FUNDAMENTALS', 'CACHE_PEERS', 'CACHE_QUARTERLY', 'ConnectionManager', 'DB_BUSY_TIMEOUT_MS', 'DB_NAME', 'DB_PATH', 'MOVERS_CACHE_TTL_SECONDS', 'OrderRequest', 'REGIME_CACHE_TTL_SECONDS', 'SQLITE_RETRY_BASE_SECONDS', 'SQLITE_WRITE_RETRIES', '_cache_invalidate', '_cache_is_fresh', '_cache_set', '_is_sqlite_lock_error', '_json_safe_clean', '_read_records', '_run_blocking', '_run_sqlite_write_with_retry', '_run_sqlite_write_with_retry_sync', '_run_ticker_blocking', 'api_logger', 'app_logger', 'blocking_io_semaphore', 'get_connection', 'manager', 'movers_cache', 'movers_cache_lock', 'portfolio_tracker', 'regime_cache', 'regime_cache_lock', 'risk_governor', 'runtime_logger', 'ticker_io_semaphore', 'update_prices_background']

import sqlite3
import pandas as pd
import numpy as np
import json
import os
import asyncio
import yfinance as yf
import time
from datetime import datetime
from typing import Any, Callable

from pydantic import BaseModel, Field
from modules.risk import RiskGovernor
from modules.tracker import PortfolioTracker
from modules.runtime_settings import runtime_settings
from modules.structured_logger import SovereignLogger
from worker.background_jobs import run_price_update_loop

runtime_logger = SovereignLogger("sovereign.runtime")
api_logger = SovereignLogger("sovereign.api")
app_logger = SovereignLogger("sovereign.app")

DB_NAME = "stocks.db"
DB_PATH = DB_NAME

DB_BUSY_TIMEOUT_MS = runtime_settings.sqlite_busy_timeout_ms
SQLITE_WRITE_RETRIES = runtime_settings.sqlite_write_retries
SQLITE_RETRY_BASE_SECONDS = runtime_settings.sqlite_retry_base_seconds
BLOCKING_IO_CONCURRENCY = runtime_settings.blocking_io_concurrency
REGIME_CACHE_TTL_SECONDS = runtime_settings.regime_cache_ttl_seconds
MOVERS_CACHE_TTL_SECONDS = runtime_settings.movers_cache_ttl_seconds
blocking_io_semaphore = asyncio.Semaphore(BLOCKING_IO_CONCURRENCY)
ticker_io_semaphore = asyncio.Semaphore(runtime_settings.ticker_io_concurrency)
portfolio_tracker = PortfolioTracker()
risk_governor = RiskGovernor()
regime_cache = {"payload": None, "timestamp": 0.0}
movers_cache = {"payload": None, "timestamp": 0.0}
regime_cache_lock = asyncio.Lock()
movers_cache_lock = asyncio.Lock()

# Caches for Audit Reports
CACHE_QUARTERLY = {}
CACHE_FUNDAMENTALS = {}
CACHE_PEERS = {}
CACHE_AUDIT_TTL = runtime_settings.audit_cache_ttl_seconds

class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1)
    side: str = Field(description="BUY or SELL")
    quantity: int = Field(default=1, ge=1)
    price: float = Field(gt=0)
    score: float = 0.0
    reason: str = "MANUAL"
    current_vix: float | None = None
    drawdown_rate_weekly: float | None = None
    portfolio_correlation: float | None = None
    projected_var_pct: float | None = None
    max_var_pct: float = 20.0

def _is_sqlite_lock_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg

async def _run_blocking(fn: Callable[..., Any], *args, **kwargs):
    async with blocking_io_semaphore:
        return await asyncio.to_thread(fn, *args, **kwargs)

async def _run_ticker_blocking(fn: Callable[..., Any], *args, **kwargs):
    async with ticker_io_semaphore:
        async with blocking_io_semaphore:
            return await asyncio.to_thread(fn, *args, **kwargs)

async def _run_sqlite_write_with_retry(write_fn: Callable[[], Any], operation_name: str):
    for attempt in range(SQLITE_WRITE_RETRIES):
        try:
            return await _run_blocking(write_fn)
        except sqlite3.OperationalError as exc:
            if _is_sqlite_lock_error(exc) and attempt < SQLITE_WRITE_RETRIES - 1:
                wait = SQLITE_RETRY_BASE_SECONDS * (2 ** attempt)
                runtime_logger.warning("SQLite lock during async write; retrying", operation=operation_name, wait_seconds=round(wait, 2), attempt=attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise

def _run_sqlite_write_with_retry_sync(write_fn: Callable[[], Any], operation_name: str):
    for attempt in range(SQLITE_WRITE_RETRIES):
        try:
            return write_fn()
        except sqlite3.OperationalError as exc:
            if _is_sqlite_lock_error(exc) and attempt < SQLITE_WRITE_RETRIES - 1:
                wait = SQLITE_RETRY_BASE_SECONDS * (2 ** attempt)
                runtime_logger.warning("SQLite lock during sync write; retrying", operation=operation_name, wait_seconds=round(wait, 2), attempt=attempt + 1)
                time.sleep(wait)
                continue
            raise

def get_connection():
    _db_url = os.getenv('DATABASE_URL', f'sqlite:///./{DB_NAME}')
    if _db_url.startswith('postgresql'):
        try:
            from sqlalchemy import create_engine
            engine = create_engine(_db_url, pool_pre_ping=True)
            return engine.raw_connection()
        except Exception as exc:
            runtime_logger.warning("PostgreSQL connection failed; falling back to SQLite", error=str(exc))
    conn = sqlite3.connect(DB_NAME, timeout=5, check_same_thread=False)
    conn.execute(f'PRAGMA busy_timeout={DB_BUSY_TIMEOUT_MS}')
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def _cache_is_fresh(cache: dict, ttl_seconds: int) -> bool:
    payload = cache.get("payload")
    ts = float(cache.get("timestamp", 0.0) or 0.0)
    return payload is not None and (time.time() - ts) < ttl_seconds

def _cache_set(cache: dict, payload: Any):
    cache["payload"] = payload
    cache["timestamp"] = time.time()

def _cache_invalidate(cache: dict):
    cache["timestamp"] = 0.0

def _read_records(query: str):
    conn = get_connection()
    try:
        df = pd.read_sql(query, conn)
        return json.loads(df.to_json(orient="records", double_precision=2))
    finally:
        conn.close()

def _json_safe_clean(obj):
    if isinstance(obj, list): return [_json_safe_clean(x) for x in obj]
    if isinstance(obj, dict): return {k: _json_safe_clean(v) for k, v in obj.items()}
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj): return None
    return obj

from fastapi import WebSocket, WebSocketDisconnect
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)

manager = ConnectionManager()

async def update_prices_background():
    await run_price_update_loop(
        get_connection=get_connection,
        run_blocking=_run_blocking,
        run_ticker_blocking=_run_ticker_blocking,
        run_sqlite_write_with_retry=_run_sqlite_write_with_retry,
        broadcast_updates=manager.broadcast,
        json_cleaner=_json_safe_clean,
        logger=runtime_logger,
    )
