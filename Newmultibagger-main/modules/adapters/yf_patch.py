import threading
import time

import yfinance as yf

from core.observability.logger import get_logger

logger = get_logger("adapters.yf_patch")

_last_yf_call_time = 0.0
_yf_lock = threading.Lock()
_original_make_request = getattr(yf.data.YfData, "_make_request", None)

def _rate_limited_make_request(self, *args, **kwargs):
    global _last_yf_call_time
    # Ensure no more than 2 requests per second globally to avoid Yahoo 429 IP Bans
    with _yf_lock:
        now = time.time()
        elapsed = now - _last_yf_call_time
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)
        _last_yf_call_time = time.time()

    return _original_make_request(self, *args, **kwargs)

if _original_make_request and not getattr(yf, "_is_patched", False):
    yf.data.YfData._make_request = _rate_limited_make_request
    yf._is_patched = True
    logger.info("Monkey-patched yfinance to enforce 2 req/sec rate limit on _make_request")
