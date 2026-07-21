# modules/fx.py
"""
Sovereign AI — Currency Conversion Utility

Single source of truth for converting monetary figures returned by data
providers (yfinance, NSE, screener.in, etc.) into INR Crore, the unit used
throughout the scoring engine and reports (``Market_Cap_Cr``, revenue_cr,
profit_cr, ...).

Why this exists
----------------
The stock universe intentionally mixes NSE/BSE-listed Indian equities with a
handful of US mega-caps (see ``ticker_list.py`` -> "GLOBAL MARKETS (US)") so
they can be ranked side by side. yfinance reports each stock's financials in
its *local listing currency* (``info["currency"]``): INR for ``.NS``/``.BO``
tickers, USD for US-listed tickers. Every call site that used to do

    market_cap_cr = raw_info.get("marketCap", 0) / 10_000_000

silently assumed the value was already in INR. For a USD-denominated ticker
this understates the true INR figure by roughly the USD/INR exchange rate
(~80-90x) because it never converts currency before dividing by 1 Crore.

This module fixes that by resolving an FX rate for any currency and applying
it before the Crore conversion.
"""

from __future__ import annotations

import time
from typing import Optional

from core.observability.logger import get_logger

logger = get_logger("modules.fx")

# Crore = 10,000,000
_CR = 10_000_000.0

# Conservative fallback used only when a live rate can't be fetched (no
# network, provider outage, unknown currency code, etc). Overridable via env
# so deployments can keep it current without a code change.
_DEFAULT_FALLBACK_RATES_TO_INR = {
    "INR": 1.0,
    "USD": 87.0,
    "EUR": 94.0,
    "GBP": 110.0,
    "JPY": 0.58,
    "HKD": 11.2,
    "CNY": 12.1,
}

_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours — FX doesn't need to be real-time
_rate_cache: dict[str, tuple[float, float]] = {}  # currency -> (rate, fetched_at)


def _fallback_rate(currency: str) -> float:
    import os

    env_key = f"FX_FALLBACK_{currency.upper()}_INR"
    override = os.environ.get(env_key)
    if override:
        try:
            return float(override)
        except ValueError:
            logger.warning(f"Invalid {env_key} override; ignoring", value=override)
    return _DEFAULT_FALLBACK_RATES_TO_INR.get(currency.upper(), 1.0)


def get_rate_to_inr(currency: str | None) -> float:
    """Return the multiplier that converts an amount in ``currency`` to INR.

    Tries a live quote first (via yfinance's ``<CCY>INR=X`` FX ticker),
    caches it in-process for ``_CACHE_TTL_SECONDS``, and falls back to a
    conservative static rate if the live lookup fails or is unavailable.
    """
    if not currency:
        return 1.0

    currency = currency.upper().strip()
    if currency == "INR":
        return 1.0

    now = time.time()
    cached = _rate_cache.get(currency)
    if cached and (now - cached[1]) < _CACHE_TTL_SECONDS:
        return cached[0]

    rate = _fetch_live_rate(currency)
    if rate is None:
        rate = _fallback_rate(currency)
        logger.debug(f"Using fallback FX rate for {currency}->INR", rate=rate)
    else:
        logger.debug(f"Fetched live FX rate for {currency}->INR", rate=rate)

    _rate_cache[currency] = (rate, now)
    return rate


def _fetch_live_rate(currency: str) -> float | None:
    """Best-effort live FX lookup. Returns None on any failure so the caller
    can fall back gracefully — this must never raise or block scoring."""
    try:
        import yfinance as yf

        ticker = yf.Ticker(f"{currency}INR=X")
        fast = getattr(ticker, "fast_info", None)
        price = None
        if fast is not None:
            price = fast.get("lastPrice") if hasattr(fast, "get") else getattr(fast, "last_price", None)
        if not price:
            info = ticker.info or {}
            price = info.get("regularMarketPrice") or info.get("previousClose")
        if price and price > 0:
            return float(price)
    except Exception as e:  # pragma: no cover - network/env dependent
        logger.debug(f"Live FX lookup failed for {currency}INR=X: {e}")
    return None


def to_inr_cr(amount: float | None, currency: str | None) -> float | None:
    """Convert a raw monetary amount (in ``currency``) to INR Crore.

    Examples:
        to_inr_cr(3_300_000_000_000, "USD") -> ~28,710,000 (Cr, at rate 87)
        to_inr_cr(1_490_00_00_000, "INR")   -> 1490.0
        to_inr_cr(None, "USD")              -> None
    """
    if amount is None:
        return None
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None

    rate = get_rate_to_inr(currency)
    return (amount * rate) / _CR
