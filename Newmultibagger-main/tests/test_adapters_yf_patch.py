import time
from unittest.mock import MagicMock, patch

import yfinance as yf


def test_yf_is_patched():
    """Importing yf_patch should set yf._is_patched = True."""

    assert getattr(yf, "_is_patched", False)


def test_make_request_is_monkey_patched():
    """The shipped patch replaces yf.data.YfData._make_request with a
    rate-limited wrapper.  Verify the method object is NOT the original."""
    import modules.adapters.yf_patch as yf_patch

    current_method = yf.data.YfData._make_request
    # The patched method should be yf_patch._rate_limited_make_request
    assert current_method is yf_patch._rate_limited_make_request


def test_rate_limit_enforced():
    """Two rapid calls should be separated by at least ~0.5 s by the patch."""
    import modules.adapters.yf_patch as yf_patch

    call_log = []

    def fake_original(self, *args, **kwargs):
        call_log.append(time.monotonic())
        return MagicMock()

    with patch.object(yf_patch, "_original_make_request", fake_original):
        dummy_self = MagicMock()
        yf_patch._rate_limited_make_request(dummy_self, "url1")
        yf_patch._rate_limited_make_request(dummy_self, "url2")

    assert len(call_log) == 2
    gap = call_log[1] - call_log[0]
    # The limiter sleeps when gap < 0.5 s, so total should be >= 0.45 s
    # (small tolerance for timer precision)
    assert gap >= 0.4, f"Expected >=0.4 s between calls, got {gap:.3f} s"
