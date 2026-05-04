# modules/cache.py
import asyncio
import time
from typing import Any

from modules.runtime_settings import runtime_settings

# In-memory caches for volatile data
regime_cache = {"payload": None, "timestamp": 0.0}
movers_cache = {"payload": None, "timestamp": 0.0}
regime_cache_lock = asyncio.Lock()
movers_cache_lock = asyncio.Lock()
REGIME_CACHE_TTL_SECONDS = runtime_settings.regime_cache_ttl_seconds
MOVERS_CACHE_TTL_SECONDS = runtime_settings.movers_cache_ttl_seconds

# Caches for Audit Reports
CACHE_QUARTERLY: dict[str, Any] = {}
CACHE_FUNDAMENTALS: dict[str, Any] = {}
CACHE_PEERS: dict[str, Any] = {}
CACHE_AUDIT_TTL = runtime_settings.audit_cache_ttl_seconds


def _cache_is_fresh(cache: dict, ttl_seconds: int) -> bool:
    payload = cache.get("payload")
    ts = float(cache.get("timestamp", 0.0) or 0.0)
    return payload is not None and (time.time() - ts) < ttl_seconds


def _cache_set(cache: dict, payload: Any):
    cache["payload"] = payload
    cache["timestamp"] = time.time()


def _cache_invalidate(cache: dict):
    cache["timestamp"] = 0.0
