"""Shared API rate limiter wiring for FastAPI routes."""
import logging
import os

logger = logging.getLogger("sovereign.rate_limit")

try:
    from limits import RateLimitItemPerMinute
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    # Prefer UPSTASH_REDIS_TCP_URL, fallback to REDIS_URL
    redis_url = os.getenv("UPSTASH_REDIS_TCP_URL") or os.getenv("REDIS_URL")
    if os.getenv("SOVEREIGN_TESTING"):
        redis_url = None

    if redis_url:
        limiter = Limiter(key_func=get_remote_address, storage_uri=redis_url)
        logger.info("slowapi limiter configured with Redis backend")
    else:
        limiter = Limiter(key_func=get_remote_address)
        logger.info("slowapi limiter configured with Memory backend")

    rate_limit_exceeded_handler = _rate_limit_exceeded_handler

    def check_api_key_rate_limit(key_hash: str, rpm_limit: int) -> bool:
        """Check if an API key has exceeded its rate limit. Returns True if exceeded."""
        return not limiter._limiter.hit(RateLimitItemPerMinute(rpm_limit), "api_key", key_hash)

except ImportError:  # pragma: no cover - slowapi is pinned, this keeps local tools importable.
    logger.warning("slowapi package is not installed; rate limiting is disabled.")
    RateLimitExceeded = None
    rate_limit_exceeded_handler = None

    class _NoopLimiter:
        def limit(self, *_args, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

    limiter = _NoopLimiter()

    def check_api_key_rate_limit(key_hash: str, rpm_limit: int) -> bool:
        """Check if an API key has exceeded its rate limit. Returns True if exceeded."""
        return False
