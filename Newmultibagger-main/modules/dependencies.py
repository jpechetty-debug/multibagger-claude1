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


from modules.data_layer.data_utils import _json_safe_clean


from fastapi import WebSocket
import os
import asyncio
import redis.asyncio as aioredis
from modules.structured_logger import SovereignLogger

logger = SovereignLogger("sovereign.websocket")
REDIS_URL = os.getenv("UPSTASH_REDIS_TCP_URL") or os.getenv("REDIS_URL") or "redis://localhost:6379/0"


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.redis = None
        self.channel = "live:prices"

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def local_broadcast(self, message: dict):
        """Send message directly to all locally connected websockets."""
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)

    async def broadcast(self, message: dict):
        """Publish message to Redis Pub/Sub so all workers receive and broadcast it."""
        published = False
        if not self.redis:
            try:
                self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
            except Exception as e:
                logger.error("Failed to initialize Redis client in broadcast", error=str(e))

        if self.redis:
            try:
                import json
                await self.redis.publish(self.channel, json.dumps(message))
                published = True
            except Exception as e:
                logger.warning("Failed to publish to Redis Pub/Sub, falling back to local broadcast", error=str(e))

        if not published:
            await self.local_broadcast(message)

    async def listen_pubsub(self):
        """Continuously listen to Redis Pub/Sub channel and broadcast messages locally."""
        while True:
            try:
                if not self.redis:
                    self.redis = aioredis.from_url(REDIS_URL, decode_responses=True)

                async with self.redis.pubsub() as pubsub:
                    await pubsub.subscribe(self.channel)
                    logger.info("WebSocket manager subscribed to Redis Pub/Sub", channel=self.channel)

                    while True:
                        try:
                            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                            if msg and msg.get("type") == "message":
                                import json
                                data = json.loads(msg["data"])
                                await self.local_broadcast(data)
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            logger.error("Error reading from Pub/Sub channel", error=str(e))
                            await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("Redis Pub/Sub listener task cancelled")
                break
            except Exception as e:
                logger.error("Redis Pub/Sub connection failed, retrying in 5 seconds", error=str(e))
                self.redis = None
                await asyncio.sleep(5)


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
