"""Shared API rate limiter wiring for FastAPI routes."""

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address)
    rate_limit_exceeded_handler = _rate_limit_exceeded_handler
except ImportError:  # pragma: no cover - slowapi is pinned, this keeps local tools importable.
    import logging
    logging.getLogger("sovereign.rate_limit").warning(
        "slowapi package is not installed; rate limiting is disabled."
    )
    RateLimitExceeded = None
    rate_limit_exceeded_handler = None

    class _NoopLimiter:
        def limit(self, *_args, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

    limiter = _NoopLimiter()
