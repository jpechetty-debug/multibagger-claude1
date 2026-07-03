"""
tests/test_fx_conversion.py
────────────────────────────
Regression tests for the USD/INR market-cap conversion bug:
previously ``raw_info.get("marketCap", 0) / 10_000_000`` was applied to
every ticker regardless of listing currency, silently understating US
mega-cap market caps (MSFT, GOOGL, META, NFLX, NVDA, ...) by roughly the
USD/INR exchange rate (~80-90x) wherever they appear in the mixed
US/India universe.

Run:
    pytest tests/test_fx_conversion.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from modules import fx  # noqa: E402
from modules.fx import get_rate_to_inr, to_inr_cr  # noqa: E402


@pytest.fixture(autouse=True)
def _clear_fx_cache():
    """The rate cache is process-global and keyed only by currency code, so
    a value cached by one test (e.g. USD -> 87.0) would otherwise leak into
    a later test that patches _fetch_live_rate to return something else."""
    fx._rate_cache.clear()
    yield
    fx._rate_cache.clear()


class TestGetRateToInr:
    def test_inr_is_identity(self):
        assert get_rate_to_inr("INR") == 1.0
        assert get_rate_to_inr("inr") == 1.0

    def test_none_or_empty_is_identity(self):
        assert get_rate_to_inr(None) == 1.0
        assert get_rate_to_inr("") == 1.0

    def test_usd_falls_back_to_static_rate_when_live_lookup_fails(self):
        with patch("modules.fx._fetch_live_rate", return_value=None):
            rate = get_rate_to_inr("USD")
        assert rate > 1.0  # must never treat USD as 1:1 with INR

    def test_uses_live_rate_when_available(self):
        with patch("modules.fx._fetch_live_rate", return_value=86.25):
            rate = get_rate_to_inr("USD")
        assert rate == 86.25


class TestToInrCr:
    def test_indian_ticker_market_cap_unchanged(self):
        # SPORTKING.NS-style: already INR. 1,490 Cr = 14,900,000,000 raw INR.
        raw = 14_900_000_000
        result = to_inr_cr(raw, "INR")
        assert result == pytest.approx(1490.0)

    def test_us_ticker_market_cap_is_converted_not_understated(self):
        # Regression for the actual bug: MSFT-style market cap in USD.
        # Old (buggy) behavior: 3_300_000_000_000 / 1e7 = 330,000 "Cr" (wrong currency).
        # Correct behavior: must scale by the USD->INR rate too.
        with patch("modules.fx._fetch_live_rate", return_value=87.0):
            raw_usd_market_cap = 3_300_000_000_000  # ~$3.3T
            result = to_inr_cr(raw_usd_market_cap, "USD")

        naive_wrong_value = raw_usd_market_cap / 10_000_000  # what the old code produced
        assert result > naive_wrong_value * 50  # must be ~87x larger, not equal
        assert result == pytest.approx(28_710_000, rel=1e-6)

    def test_none_amount_returns_none(self):
        assert to_inr_cr(None, "USD") is None

    def test_zero_amount_returns_zero(self):
        assert to_inr_cr(0, "USD") == 0.0

    def test_missing_currency_defaults_to_no_conversion(self):
        # Conservative: if currency is unknown, don't invent a rate.
        # 1,490 Cr expressed as raw units = 1490 * 1e7 = 14,900,000,000.
        assert to_inr_cr(14_900_000_000, None) == pytest.approx(1490.0)
