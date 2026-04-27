# modules/cache.py
import time
import asyncio
from typing import Any
from modules.runtime_settings import runtime_settings

# In-memory caches for volatile data
regime_cache = {"payload": None, "timestamp": 0.0}
movers_cache = {"payload": None, "timestamp": 0.0}
regime_cache_lock = asyncio.Lock()
movers_cache_lock = asyncio.Lock()

# Caches for Audit Reports
CACHE_QUARTERLY = {}
CACHE_FUNDAMENTALS = {}
CACHE_PEERS = {}
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
