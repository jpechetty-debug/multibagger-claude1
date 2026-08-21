"""
Redis Cache layer for Sovereign workers with in-memory fallback.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from core.observability.logger import get_logger

logger = get_logger("sovereign.worker.cache")


class RedisCache:
    """Redis cache with local memory fallback."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        self._client: Any = None
        self._memory_store: dict[str, tuple[Any, float | None]] = {}
        self._init_client()

    def _init_client(self) -> None:
        try:
            import redis
            self._client = redis.Redis.from_url(self.redis_url, decode_responses=True)
            self._client.ping()
        except Exception as e:
            logger.warning("redis.unavailable_using_memory_fallback", error=str(e))
            self._client = None

    def get(self, key: str) -> Any:
        if self._client is not None:
            try:
                val = self._client.get(key)
                if val is not None:
                    return json.loads(val)
                return None
            except Exception as e:
                logger.warning("redis.get_failed", key=key, error=str(e))
        
        # Memory fallback
        if key in self._memory_store:
            val, expiry = self._memory_store[key]
            if expiry is None or time.time() < expiry:
                return val
            del self._memory_store[key]
        return None

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        if self._client is not None:
            try:
                serialized = json.dumps(value)
                if ttl:
                    self._client.setex(key, ttl, serialized)
                else:
                    self._client.set(key, serialized)
                return
            except Exception as e:
                logger.warning("redis.set_failed", key=key, error=str(e))

        expiry = time.time() + ttl if ttl else None
        self._memory_store[key] = (value, expiry)

    def delete(self, key: str) -> None:
        if self._client is not None:
            try:
                self._client.delete(key)
            except Exception:
                pass
        self._memory_store.pop(key, None)

    def get_stock_score(self, symbol: str) -> dict | None:
        return self.get(f"stock_score:{symbol.upper()}")

    def cache_stock_score(self, symbol: str, data: dict, ttl: int = 3600) -> None:
        self.set(f"stock_score:{symbol.upper()}", data, ttl=ttl)

    def get_regime(self) -> dict | None:
        return self.get("market_regime")

    def cache_regime(self, data: dict, ttl: int = 3600) -> None:
        self.set("market_regime", data, ttl=ttl)


cache = RedisCache()
