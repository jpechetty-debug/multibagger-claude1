# modules/cache.py
"""
Sovereign AI Trading Engine — Distributed Caching Layer
Refactored to use Redis for multi-worker compatibility (Gunicorn/Celery).
Falls back to in-memory if Redis is unavailable via SovereignCache.
"""
import asyncio
import functools
import inspect
from collections.abc import Callable
from typing import Any, Optional

from modules.runtime_settings import runtime_settings
from worker.redis_cache import cache as redis_cache, DEFAULT_TTL

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

class DistributedAsyncLock:
    def __init__(self, key: str, timeout: int = 10):
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.acquired = False
        self._local_lock = asyncio.Lock()

    async def __aenter__(self):
        if not redis_cache.is_connected():
            await self._local_lock.acquire()
            self.acquired = True
            return self

        for _ in range(self.timeout * 10):
            acquired = await asyncio.to_thread(
                redis_cache._redis.set, self.key, "1", nx=True, ex=self.timeout
            ) if redis_cache._redis else False
            if acquired:
                self.acquired = True
                return self
            await asyncio.sleep(0.1)
        # Instead of raising timeout, fallback or proceed
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.acquired:
            if not redis_cache.is_connected():
                self._local_lock.release()
            elif redis_cache._redis:
                await asyncio.to_thread(redis_cache._redis.delete, self.key)
            self.acquired = False

regime_cache_lock = DistributedAsyncLock("regime_cache")
movers_cache_lock = DistributedAsyncLock("movers_cache")

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

def cached(ttl: int | None = None, key_prefix: str = "fn"):
    """
    Decorator to cache function results in Redis.
    Generates key based on function name and arguments.
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Generate stable cache key
            try:
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()
                # Skip 'self' or 'cls' for methods if needed, but here we assume general functions
                arg_str = ":".join(f"{k}={v}" for k, v in bound_args.arguments.items() if k not in ("self", "cls"))
                cache_key = f"{key_prefix}:{func.__name__}:{arg_str}"
            except Exception:
                # Fallback key generation
                cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"

            # Try to get from cache
            cached_val = redis_cache.get(cache_key)
            if cached_val is not None:
                return cached_val

            # Execute function
            result = func(*args, **kwargs)

            # Store in cache
            ttl_val = ttl if ttl is not None else DEFAULT_TTL
            redis_cache.set(cache_key, result, ttl=ttl_val)

            return result
        return wrapper
    return decorator
