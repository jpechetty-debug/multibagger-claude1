# modules/financial_adapter.py
"""
Sovereign AI — Financial Data Adapter

Decouples raw Yahoo Finance DataFrame extraction from business logic.
The adapter normalizes messy, inconsistently-named DataFrames into a
clean typed dataclass so the CAGR engine and fundamentals module can
be pure math functions that are trivially unit-testable.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from core.observability.logger import get_logger

_log = get_logger(__name__)


logger = logging.getLogger(__name__)


@dataclass
class NormalizedFinancials:
    """Clean, typed representation of a company's financial history.

    All series are oldest-first dicts keyed by year string:
        {"2020": 50000, "2021": 60000, "2022": 72000, "2023": 85000}
    """

    revenue_series: dict[str, float] = field(default_factory=dict)
    net_income_series: dict[str, float] = field(default_factory=dict)
    shares_outstanding_series: dict[str, float] = field(default_factory=dict)
    total_assets_series: dict[str, float] = field(default_factory=dict)
    equity_series: dict[str, float] = field(default_factory=dict)
    data_points: int = 0


class FundamentalsProvider(ABC):
    """Provider boundary for point-in-time fundamentals."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name used for routing and audit logs."""

    @abstractmethod
    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Return canonical fundamental data for one symbol."""


class _AdapterFundamentalsProvider(FundamentalsProvider):
    """Wrap existing DataProvider implementations behind this module's interface."""

    def __init__(self, provider: Any):
        self.provider = provider

    @property
    def name(self) -> str:
        return str(self.provider.name)

    @property
    def available(self) -> bool:
        return bool(getattr(self.provider, "available", True))

    @available.setter
    def available(self, value: bool) -> None:
        self.provider.available = value

    @property
    def fail_streak(self) -> int:
        return int(getattr(self.provider, "fail_streak", 0))

    @fail_streak.setter
    def fail_streak(self, value: int) -> None:
        self.provider.fail_streak = value

    @property
    def cooldown_until(self) -> float:
        return float(getattr(self.provider, "cooldown_until", 0.0))

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        return await self.provider.fetch_fundamentals(symbol)  # type: ignore

    async def safe_fetch(self, symbol: str) -> dict[str, Any] | None:
        return await self.provider.safe_fetch(symbol)  # type: ignore


def create_fundamentals_provider(
    name: str | None = None,
    *,
    executor: Any = None,
) -> FundamentalsProvider:
    """Create the primary fundamentals provider.

    Switching providers is intentionally one line:
    ``FUNDAMENTALS_PROVIDER=screener_in|pnsea|nsepython``.
    yFinance is intentionally absent here; it remains a price/history fallback.
    """
    provider_name = (name or os.getenv("FUNDAMENTALS_PROVIDER", "screener_in")).lower()  # type: ignore

    if provider_name == "screener":
        provider_name = "screener_in"

    if provider_name == "screener_in":
        from modules.adapters.screener_in import ScreenerInProvider

        return _AdapterFundamentalsProvider(ScreenerInProvider(executor))
    if provider_name == "pnsea":
        from modules.adapters.nse import PNSEAProvider

        return _AdapterFundamentalsProvider(PNSEAProvider(executor))
    if provider_name == "nsepython":
        from modules.adapters.nse import NSEPythonProvider

        return _AdapterFundamentalsProvider(NSEPythonProvider(executor))

    raise ValueError(
        "Unknown FUNDAMENTALS_PROVIDER="
        f"{provider_name!r}; expected screener_in, pnsea, or nsepython"
    )


# ── Fuzzy Key Extraction ──────────────────────────────────────────────────────

_REVENUE_KEYS = [
    "Total Revenue",
    "Operating Revenue",
    "Revenue From Operations",
    "Net Sales",
]

_NET_INCOME_KEYS = [
    "Net Income",
    "Net Profit",
    "PAT",
    "Profit After Tax",
]

_SHARES_KEYS = [
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock",
]

_TOTAL_ASSETS_KEYS = [
    "Total Assets",
]

_EQUITY_KEYS = [
    "Stockholders Equity",
    "Common Stock Equity",
    "Total Equity",
    "Shareholders Equity",
]

_FIELD_KEY_CANDIDATES = {
    "revenue": _REVENUE_KEYS,
    "net_income": _NET_INCOME_KEYS,
    "shares": _SHARES_KEYS,
    "total_assets": _TOTAL_ASSETS_KEYS,
    "equity": _EQUITY_KEYS,
}

_SOURCE_KEY_PREFS = {
    "screener": {
        "revenue": "Revenue From Operations",
        "net_income": "Net Profit",
    },
    "screener_in": {
        "revenue": "Revenue From Operations",
        "net_income": "Net Profit",
    },
    "yfinance": {
        "revenue": "Total Revenue",
        "net_income": "Net Income",
        "shares": "Ordinary Shares Number",
        "total_assets": "Total Assets",
        "equity": "Stockholders Equity",
    },
}


def _extract_series(
    df: pd.DataFrame,
    keys: list[str],
    *,
    field: str | None = None,
    source: str = "yfinance",
) -> pd.Series | None:
    """Extract a time-series row using exact then fuzzy matching."""
    if df is None or df.empty:
        return None

    source = (source or "unknown").lower()
    preferred = _SOURCE_KEY_PREFS.get(source, {}).get(field or "")
    exact_hits = [key for key in keys if key in df.index]

    if len(exact_hits) > 1:
        logger.warning(
            "financial_key_conflict | field=%s source=%s found=%s using=%s",
            field or "unknown",
            source,
            exact_hits,
            preferred if preferred in exact_hits else exact_hits[0],
        )

    if preferred and preferred in df.index:
        return df.loc[preferred]

    for key in exact_hits:
        return df.loc[key]

    # Fuzzy fallback. Yahoo Finance statements often carry several close
    # variants of the same line item (e.g. "Net Income", "Net Income
    # Continuing Operations", "Net Income Applicable To Common Shares").
    # Returning the first substring match in DataFrame row order is
    # order-dependent and can silently select a derived/adjusted figure
    # instead of the headline one — exactly when data is messiest and a
    # wrong pick is least likely to be noticed. Prefer the shortest
    # matching label instead, which is closest to the canonical name.
    for key in keys:
        candidates = [idx_name for idx_name in df.index if key.lower() in idx_name.lower()]
        if candidates:
            best = min(candidates, key=len)
            if len(candidates) > 1:
                logger.debug(
                    "financial_key_fuzzy_match | field=%s key=%s candidates=%s using=%s",
                    field or "unknown", key, candidates, best,
                )
            return df.loc[best]

    return None


def _series_to_dict(series: pd.Series | None) -> dict[str, float]:
    """Convert a pandas Series to a year-keyed dict, oldest first."""
    if series is None:
        return {}

    result = {}
    for col in series.index:
        year_key = col.strftime("%Y") if hasattr(col, "strftime") else str(col)
        val = series[col]
        if pd.notna(val):
            result[year_key] = float(val)

    # Reverse to oldest-first if the first key is newer than the last
    keys = list(result.keys())
    if len(keys) >= 2 and keys[0] > keys[-1]:
        result = dict(reversed(list(result.items())))

    return result


def extract_normalized_financials(ticker, *, source: str = "yfinance") -> NormalizedFinancials:
    """Extract and normalize financial data from a provider ticker-like object.

    **Legacy yFinance path.** This function wraps the yFinance ``Ticker``
    object shape (``ticker.financials``, ``ticker.balance_sheet`` DataFrames)
    and is used only by the CAGR engine as a fallback when Screener.in data
    is unavailable.

    The primary fundamentals flow uses ``create_fundamentals_provider()``
    which routes to ``ScreenerInProvider`` (or ``PNSEAProvider`` /
    ``NSEPythonProvider`` via the ``FUNDAMENTALS_PROVIDER`` env var).

    This is the single place where fuzzy key matching happens.
    Downstream code receives clean, typed data.
    """
    try:
        fin = ticker.financials
        if fin is None or (isinstance(fin, pd.DataFrame) and fin.empty):
            return NormalizedFinancials()
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return NormalizedFinancials()

    try:
        bs = ticker.balance_sheet
        if bs is None or (isinstance(bs, pd.DataFrame) and bs.empty):
            bs = pd.DataFrame()
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        bs = pd.DataFrame()

    revenue = _series_to_dict(
        _extract_series(fin, _REVENUE_KEYS, field="revenue", source=source)
    )
    net_income = _series_to_dict(
        _extract_series(fin, _NET_INCOME_KEYS, field="net_income", source=source)
    )
    shares = _series_to_dict(
        _extract_series(bs, _SHARES_KEYS, field="shares", source=source)
    )
    total_assets = _series_to_dict(
        _extract_series(bs, _TOTAL_ASSETS_KEYS, field="total_assets", source=source)
    )
    equity = _series_to_dict(
        _extract_series(bs, _EQUITY_KEYS, field="equity", source=source)
    )

    data_points = max(len(revenue), len(net_income), 0)

    return NormalizedFinancials(
        revenue_series=revenue,
        net_income_series=net_income,
        shares_outstanding_series=shares,
        total_assets_series=total_assets,
        equity_series=equity,
        data_points=data_points,
    )
