# modules/dependencies.py
"""
Sovereign Terminal — Dependency Facade
Modularized into: auth.py, connections.py, cache.py, models.py
"""

import json
from typing import Any

import pandas as pd

from modules.cache import (
    _cache_invalidate,
    _cache_is_fresh,
    _cache_set,
    MOVERS_CACHE_TTL_SECONDS,
    REGIME_CACHE_TTL_SECONDS,
    CACHE_QUARTERLY as CACHE_QUARTERLY_VAL,
    CACHE_FUNDAMENTALS as CACHE_FUNDAMENTALS_VAL,
    CACHE_AUDIT_TTL,
    movers_cache,
    movers_cache_lock,
    regime_cache,
    regime_cache_lock,
)
CACHE_QUARTERLY = CACHE_QUARTERLY_VAL
CACHE_FUNDAMENTALS = CACHE_FUNDAMENTALS_VAL
# -- Re-exporting from Modular Components --
from db.db_core import db_engine, get_db_connection as get_sqla_connection
from modules.connections import (
    _run_blocking,
    _run_sqlite_write_with_retry,
    _run_sqlite_write_with_retry_sync,
    _run_ticker_blocking,
    get_connection,
)
from modules.runtime_settings import runtime_settings
from modules.structured_logger import SovereignLogger
from worker.background_jobs import run_price_update_loop
from modules.models import OrderRequest

from modules.auth import get_api_key
# Legacy Loggers (Prefer direct import from structured_logger in new code)
runtime_logger = SovereignLogger("sovereign.runtime")
api_logger = SovereignLogger("sovereign.api")
app_logger = SovereignLogger("sovereign.app")

# Remaining Domain Instances
from modules.risk import RiskGovernor
from modules.tracker import PortfolioTracker

portfolio_tracker = PortfolioTracker()
risk_governor = RiskGovernor()


def _read_records(query: str, params: dict[Any, Any] | None = None):
    """Executes a SQL query using SQLAlchemy and returns JSON-friendly dictionary list."""
    with get_sqla_connection() as conn:
        from sqlalchemy import text

        df = pd.read_sql(text(query), conn, params=params)
        return json.loads(df.to_json(orient="records", double_precision=2))


def _json_safe_clean(obj):
    import numpy as np
    import pandas as pd

    # Handle Pydantic models (v1 and v2)
    if hasattr(obj, "dict") and callable(obj.dict):
        obj = obj.dict()
    elif hasattr(obj, "model_dump") and callable(obj.model_dump):
        obj = obj.model_dump()

    if isinstance(obj, (list, tuple, np.ndarray)):
        return [_json_safe_clean(x) for x in obj]
    if isinstance(obj, (dict, pd.Series)):
        return {str(k): _json_safe_clean(v) for k, v in obj.items()}
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    if isinstance(obj, (np.integer, np.floating)):
        val = obj.item()
        if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
            return None
        return val
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


async def refresh_prices_once():
    await run_price_update_loop(
        get_connection=get_connection,
        run_blocking=_run_blocking,
        run_ticker_blocking=_run_ticker_blocking,
        run_sqlite_write_with_retry=_run_sqlite_write_with_retry,
        broadcast_updates=manager.broadcast,
        json_cleaner=_json_safe_clean,
        logger=runtime_logger,
        startup_delay_seconds=0,
        run_once=True,
    )
