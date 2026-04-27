# modules/dependencies.py
"""
Sovereign Terminal — Dependency Facade
Modularized into: auth.py, connections.py, cache.py, models.py
"""
import json
import pandas as pd
from typing import Any

from modules.structured_logger import SovereignLogger
from worker.background_jobs import run_price_update_loop

# -- Re-exporting from Modular Components --
from modules.auth import get_api_key
from modules.connections import (
    get_connection, get_sqla_connection, _run_blocking, _run_ticker_blocking,
    _run_sqlite_write_with_retry, _run_sqlite_write_with_retry_sync,
    DB_NAME, DB_PATH, blocking_io_semaphore, ticker_io_semaphore
)
from modules.cache import (
    regime_cache, movers_cache, regime_cache_lock, movers_cache_lock,
    CACHE_QUARTERLY, CACHE_FUNDAMENTALS, CACHE_PEERS, CACHE_AUDIT_TTL,
    _cache_is_fresh, _cache_set, _cache_invalidate
)
from modules.models import OrderRequest

# Legacy Loggers (Prefer direct import from structured_logger in new code)
runtime_logger = SovereignLogger("sovereign.runtime")
api_logger = SovereignLogger("sovereign.api")
app_logger = SovereignLogger("sovereign.app")

# Remaining Domain Instances
from modules.risk import RiskGovernor
from modules.tracker import PortfolioTracker
portfolio_tracker = PortfolioTracker()
risk_governor = RiskGovernor()

def _read_records(query: str, params: dict = None):
    """Executes a SQL query using SQLAlchemy and returns JSON-friendly dictionary list."""
    with get_sqla_connection() as conn:
        from sqlalchemy import text
        df = pd.read_sql(text(query), conn, params=params)
        return json.loads(df.to_json(orient="records", double_precision=2))

def _json_safe_clean(obj):
    import numpy as np
    if isinstance(obj, list): return [_json_safe_clean(x) for x in obj]
    if isinstance(obj, dict): return {k: _json_safe_clean(v) for k, v in obj.items()}
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj): return None
    return obj

from fastapi import WebSocket
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
