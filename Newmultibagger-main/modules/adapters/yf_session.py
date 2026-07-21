import os
from requests import Session
from requests_cache import CacheMixin, SQLiteCache
from requests_ratelimiter import LimiterMixin
from pyrate_limiter import Duration, Rate, Limiter
from core.observability.logger import get_logger

logger = get_logger("adapters.yf_session")

class CachedLimiterSession(CacheMixin, LimiterMixin, Session):
    pass

_yf_session = None

def get_yf_session():
    """Returns a singleton CachedLimiterSession for yfinance to avoid IP bans."""
    global _yf_session
    if _yf_session is None:
        try:
            # Place cache in runtime dir
            cache_dir = os.path.join(os.path.dirname(__file__), "..", "..", "runtime")
            os.makedirs(cache_dir, exist_ok=True)
            cache_path = os.path.join(cache_dir, "yfinance_cache")

            _yf_session = CachedLimiterSession(
                # Allow 2 requests per second to avoid Yahoo Finance 429 Too Many Requests
                limiter=Limiter(Rate(2, Duration.SECOND)),
                backend=SQLiteCache(cache_path),
                expire_after=43200, # 12 hours caching
            )
            # Yfinance needs a proper User-Agent to avoid generic bot blocks
            _yf_session.headers['User-agent'] = 'sovereign-trading-engine/2.0'
            logger.info("Initialized rate-limited cached session for yfinance")
        except Exception as e:
            logger.error(f"Failed to initialize yf_session: {e}")
            _yf_session = None
    return _yf_session
