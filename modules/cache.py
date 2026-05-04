# modules/cache.py
"""
Sovereign AI Trading Engine — Distributed Caching Layer
Refactored to use Redis for multi-worker compatibility (Gunicorn/Celery).
Falls back to in-memory if Redis is unavailable via SovereignCache.
"""
import asyncio
from typing import Any

from modules.runtime_settings import runtime_settings
from worker.redis_cache import cache as redis_cache

# TTL Settings from Runtime Configuration
REGIME_CACHE_TTL_SECONDS = runtime_settings.regime_cache_ttl_seconds
MOVERS_CACHE_TTL_SECONDS = runtime_settings.movers_cache_ttl_seconds
CACHE_AUDIT_TTL = runtime_settings.audit_cache_ttl_seconds

class RedisCacheProxy:
    """
    A proxy object that mimics a dictionary but interfaces with Redis.
    Maintains compatibility with legacy code expecting deps.regime_cache['payload'].
    """
    def __init__(self, key: str, ttl: int):
        self.key = key
        self.ttl = ttl

    def __getitem__(self, item):
        data = redis_cache.get(self.key)
        if isinstance(data, dict):
            return data.get(item)
        return None

    def get(self, item, default=None):
        val = self[item]
        return val if val is not None else default

    def set_payload(self, payload: Any):
        import time
        redis_cache.set(self.key, {"payload": payload, "timestamp": time.time()}, ttl=self.ttl)

    def invalidate(self):
        redis_cache.delete(self.key)

    def is_fresh(self, ttl_override: int = None) -> bool:
        import time
        data = redis_cache.get(self.key)
        if not data or not isinstance(data, dict):
            return False
        
        ts = data.get("timestamp", 0.0)
        ttl = ttl_override if ttl_override is not None else self.ttl
        return (time.time() - ts) < ttl

# Distributed cache proxies
regime_cache = RedisCacheProxy("regime_status", REGIME_CACHE_TTL_SECONDS)
movers_cache = RedisCacheProxy("market_movers", MOVERS_CACHE_TTL_SECONDS)

# Audit Caches (Namespaced keys)
CACHE_QUARTERLY = "audit:quarterly"
CACHE_FUNDAMENTALS = "audit:fundamentals"
CACHE_PEERS = "audit:peers"

# Distributed Locks: asyncio.Lock() is NOT safe for multi-worker.
# For simple cache-aside patterns, we use a no-op lock to maintain API compatibility
# while allowing Redis to handle the data consistency.
class NoOpLock:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass

regime_cache_lock = NoOpLock()
movers_cache_lock = NoOpLock()

def _cache_is_fresh(cache_obj: Any, ttl_seconds: int) -> bool:
    if isinstance(cache_obj, RedisCacheProxy):
        return cache_obj.is_fresh(ttl_override=ttl_seconds)
    # Fallback for raw keys (Audit caches)
    data = redis_cache.get(str(cache_obj))
    if data and isinstance(data, dict):
        import time
        return (time.time() - data.get("timestamp", 0.0)) < ttl_seconds
    return False

def _cache_set(cache_obj: Any, payload: Any):
    if isinstance(cache_obj, RedisCacheProxy):
        cache_obj.set_payload(payload)
    else:
        # For Audit caches
        import time
        redis_cache.set(str(cache_obj), {"payload": payload, "timestamp": time.time()}, ttl=CACHE_AUDIT_TTL)

def _cache_invalidate(cache_obj: Any):
    if isinstance(cache_obj, RedisCacheProxy):
        cache_obj.invalidate()
    else:
        redis_cache.delete(str(cache_obj))
