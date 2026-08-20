# modules/cache.py
"""
Sovereign AI Trading Engine — Caching Layer
Local in-memory cache since Redis has been removed for the local Sovereign Terminal.
"""
import asyncio
import functools
import inspect
import time
from collections.abc import Callable
from typing import Any

from core.observability.logger import get_logger
from modules.runtime_settings import runtime_settings

_log = get_logger(__name__)

# TTL Settings from Runtime Configuration
REGIME_CACHE_TTL_SECONDS = runtime_settings.regime_cache_ttl_seconds
MOVERS_CACHE_TTL_SECONDS = runtime_settings.movers_cache_ttl_seconds
CACHE_AUDIT_TTL = runtime_settings.audit_cache_ttl_seconds
DEFAULT_TTL = 3600

_memory_store = {}

class MemoryCacheProxy:
    """
    A proxy object that mimics a dictionary for in-memory caching.
    """
    def __init__(self, key: str, ttl: int):
        self.key = key
        self.ttl = ttl

    def __getitem__(self, item):
        data = _memory_store.get(self.key)
        if isinstance(data, dict):
            if time.time() - data.get("timestamp", 0) <= self.ttl:
                return data.get("payload", {}).get(item)
            else:
                self.invalidate()
        return None

    def get(self, item, default=None):
        val = self[item]
        return val if val is not None else default

    def set_payload(self, payload: Any):
        _memory_store[self.key] = {"payload": payload, "timestamp": time.time()}

    def invalidate(self):
        _memory_store.pop(self.key, None)

    def is_fresh(self, ttl_override: int = None) -> bool:
        data = _memory_store.get(self.key)
        if not data or not isinstance(data, dict):
            return False
        ts = data.get("timestamp", 0.0)
        ttl = ttl_override if ttl_override is not None else self.ttl
        return (time.time() - ts) < ttl

# Distributed cache proxies (now just local in-memory)
regime_cache = MemoryCacheProxy("regime_status", REGIME_CACHE_TTL_SECONDS)
movers_cache = MemoryCacheProxy("market_movers", MOVERS_CACHE_TTL_SECONDS)
cache_audit = MemoryCacheProxy("cache_audit", CACHE_AUDIT_TTL)

# Audit Caches (Namespaced keys)
CACHE_QUARTERLY = "audit:quarterly"
CACHE_FUNDAMENTALS = "audit:fundamentals"
CACHE_PEERS = "audit:peers"

class DistributedAsyncLock:
    def __init__(self, key: str, timeout: int = 10):
        self.key = f"lock:{key}"
        self._local_lock = asyncio.Lock()

    async def __aenter__(self):
        await self._local_lock.acquire()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._local_lock.release()

regime_cache_lock = DistributedAsyncLock("regime_cache")
movers_cache_lock = DistributedAsyncLock("movers_cache")

def _cache_is_fresh(cache_obj: Any, ttl_seconds: int) -> bool:
    if isinstance(cache_obj, MemoryCacheProxy):
        return cache_obj.is_fresh(ttl_override=ttl_seconds)
    
    data = _memory_store.get(str(cache_obj))
    if not data or not isinstance(data, dict):
        return False
    return (time.time() - data.get("timestamp", 0.0)) < ttl_seconds

def _cache_set(cache_obj: Any, payload: Any):
    if isinstance(cache_obj, MemoryCacheProxy):
        cache_obj.set_payload(payload)
    else:
        _memory_store[str(cache_obj)] = {"payload": payload, "timestamp": time.time()}

def _cache_invalidate(cache_obj: Any):
    if isinstance(cache_obj, MemoryCacheProxy):
        cache_obj.invalidate()
    else:
        _memory_store.pop(str(cache_obj), None)

def _generate_cache_key(func, key_prefix, args, kwargs):
    try:
        sig = inspect.signature(func)
        bound_args = sig.bind(*args, **kwargs)
        bound_args.apply_defaults()
        arg_str = ":".join(f"{k}={v}" for k, v in bound_args.arguments.items() if k not in ("self", "cls"))
        return f"{key_prefix}:{func.__name__}:{arg_str}"
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return f"{key_prefix}:{func.__name__}:{hash(str(args) + str(kwargs))}"

def cached(ttl: int | None = None, key_prefix: str = "fn"):
    """
    Decorator to cache function results in memory.
    """
    def decorator(func: Callable):
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                cache_key = _generate_cache_key(func, key_prefix, args, kwargs)
                
                data = _memory_store.get(cache_key)
                ttl_val = ttl if ttl is not None else DEFAULT_TTL
                if data and isinstance(data, dict) and (time.time() - data.get("timestamp", 0) <= ttl_val):
                    return data.get("payload")
                    
                result = await func(*args, **kwargs)
                _memory_store[cache_key] = {"payload": result, "timestamp": time.time()}
                return result
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                cache_key = _generate_cache_key(func, key_prefix, args, kwargs)
                
                data = _memory_store.get(cache_key)
                ttl_val = ttl if ttl is not None else DEFAULT_TTL
                if data and isinstance(data, dict) and (time.time() - data.get("timestamp", 0) <= ttl_val):
                    return data.get("payload")
                    
                result = func(*args, **kwargs)
                _memory_store[cache_key] = {"payload": result, "timestamp": time.time()}
                return result
            return sync_wrapper
    return decorator
