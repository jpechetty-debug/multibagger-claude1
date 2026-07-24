# modules/adapters/nse_xbrl_provider.py
"""
NSE Integrated Filing (XBRL) data adapter.

Wraps the `nse-xbrl` package (https://github.com/ShantanuAnant/nse-xbrl) to
pull audited, official financial-statement figures straight from NSE's
"Integrated Filing - Financials" XBRL documents, rather than relying only on
third-party scrapes or yFinance's free-tier depth limit.

What this adapter uniquely provides:
  - Official balance sheet figures (Total Equity, financial liabilities,
    shares outstanding, etc.) straight from the audited filing.
  - Trailing-twelve-month Sales_Growth_TTM% / EPS_Growth% computed from raw
    quarterly revenue/PAT/EPS across up to 8 filings (~2 years), instead of a
    single pre-computed ratio from a third party.
  - Debt_Equity, Book_Value, and ROE% computed directly from the filed
    balance sheet + trailing 4-quarter PAT.

What it deliberately does NOT provide — NSE's Integrated Filing XBRL doesn't
tag these cleanly, and guessing would be worse than leaving them blank:
  - CFO / CFO_PAT_Ratio. The cash-flow context only tags a handful of
    sub-line-items (capex, dividends paid, tax paid, interest received, net
    change in cash, "other investing", "other financing") — not a clean
    "cash from operating activities" total. Reconstructing CFO from those
    parts would require assuming everything unlisted nets to zero, which is
    not a safe assumption. Left out so a downstream provider (Screener.in)
    supplies it instead.
  - 5Y/10Y CAGR. NSE's Integrated Filing format only exists since 2024, so
    this filing type alone can't yet provide 5 years of history. Only TTM
    growth is computed here; combine with Screener.in for longer CAGR.
  - Sector/industry, promoter holding, F-Score — not part of this filing.

Because of the gaps above, this provider is intentionally positioned AFTER
ScreenerInProvider in the fallback chain (see data_service.py): when
Screener.in is reachable it remains the richer primary source for CAGR/CFO;
this provider is the redundancy/fallback that activates when Screener is
blocked, rate-limited, or missing a company — and its officially-filed
figures are still meaningfully more precise than the older bhavcopy /
NSEPython fallbacks it displaces in the chain.

Auth: cookie-based and fragile — cookies are copied from a real browser
session and typically expire within hours (see nse_xbrl.NSEClient's
docstring for how to obtain them). Set the NSE_COOKIE environment variable.
If it's unset, or the `nse-xbrl` package isn't installed, this provider
disables itself at construction time — same soft-dependency pattern as
ScreenerInProvider.
"""

from __future__ import annotations

import asyncio
import os
import re
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.observability.logger import get_logger

from .base import DataProvider

if TYPE_CHECKING:
    from nse_xbrl import FilingResult, NSEClient

logger = get_logger("adapters.nse_xbrl")

try:
    from nse_xbrl import NSEClient as _NSEClient
    _NSE_XBRL_AVAILABLE = True
except ImportError:
    _NSEClient = None  # type: ignore[assignment, misc]
    _NSE_XBRL_AVAILABLE = False
    logger.warning("nse-xbrl not installed — NSEXBRLProvider will not be available")

# Up to 8 quarterly filings (~2 years) — enough for a TTM-vs-prior-TTM growth
# comparison without hammering NSE for a full history it doesn't have anyway.
NSE_XBRL_MAX_FILINGS = int(os.getenv("NSE_XBRL_MAX_FILINGS", "8"))

# SEBI requires quarterly results be filed within 45 days of quarter-end.
# This filing type has no separate "announcement date" field, so As_Of_Date
# is estimated conservatively as period_end + this lag — it will always be
# >= the true announcement date, which is the safe direction for the PIT gate
# (it never lets scoring see data earlier than it could plausibly exist).
NSE_XBRL_PIT_LAG_DAYS = int(os.getenv("NSE_XBRL_PIT_LAG_DAYS", "45"))


def _clean_symbol(symbol: str) -> str:
    """Strip exchange suffixes: RELIANCE.NS -> RELIANCE."""
    return re.sub(r"\.(NS|BO|BSE)$", "", symbol.strip().upper())


def _resolve_issuer_name(client: "NSEClient", symbol: str) -> str | None:
    """Resolve a trading symbol to NSE's registered company (issuer) name.

    `NSEClient.fetch_financials()` requires the issuer's full legal name
    alongside the symbol — NSE's filing-listing endpoint is keyed on both.
    This reuses the client's authenticated session and retry/re-seed logic
    via its internal `_get()` helper rather than opening a second,
    unauthenticated session against a different endpoint.
    """
    try:
        data = client._get(
            "/quote-equity",
            params={"symbol": symbol},
            referer_path=f"/get-quotes/equity?symbol={symbol}",
        )
    except Exception as exc:
        logger.warning(f"NSE issuer-name lookup failed for {symbol}: {exc}")
        return None
    if not isinstance(data, dict):
        return None
    info = data.get("info", {})
    if not isinstance(info, dict):
        return None
    name = info.get("companyName")
    return str(name) if name else None


def _ttm_pair(filings: list["FilingResult"], attr: str) -> tuple[float, float] | None:
    """Sum of the most recent 4 quarters' `attr` vs. the prior 4 quarters.

    `filings` must already be sorted most-recent-first. Requires all 8
    values present — returns None rather than growth computed from a
    partial window, which would silently mix quarter-counts.
    """
    if len(filings) < 8:
        return None
    values = [getattr(f, attr, None) for f in filings[:8]]
    if any(v is None for v in values):
        return None
    recent_4 = sum(values[:4])
    prior_4 = sum(values[4:8])
    return recent_4, prior_4


def _ttm_growth_pct(filings: list["FilingResult"], attr: str) -> float | None:
    pair = _ttm_pair(filings, attr)
    if pair is None:
        return None
    recent_4, prior_4 = pair
    if not prior_4:
        return None
    return round(((recent_4 - prior_4) / abs(prior_4)) * 100.0, 2)


def _ttm_sum(filings: list["FilingResult"], attr: str) -> float | None:
    """Sum of `attr` across the most recent 4 quarters, or None if incomplete."""
    if len(filings) < 4:
        return None
    values = [getattr(f, attr, None) for f in filings[:4]]
    if any(v is None for v in values):
        return None
    return sum(values)


class NSEXBRLProvider(DataProvider):
    """Official NSE Integrated Filing (XBRL) fundamentals — see module docstring."""

    @property
    def name(self) -> str:
        return "nse_xbrl"

    def __init__(self, executor=None):
        super().__init__()
        self.executor = executor
        self._client: "NSEClient | None" = None

        if not _NSE_XBRL_AVAILABLE:
            self.available = False
            return
        if not os.environ.get("NSE_COOKIE"):
            self.available = False
            logger.warning(
                "NSEXBRLProvider disabled — set the NSE_COOKIE environment "
                "variable (see nse_xbrl.NSEClient's docstring for how to "
                "copy one from a browser session)."
            )

    def _get_client(self) -> "NSEClient":
        if self._client is None:
            self._client = _NSEClient()
        return self._client

    def _fetch_sync(self, symbol: str) -> dict[str, Any]:
        clean = _clean_symbol(symbol)
        client = self._get_client()

        issuer = _resolve_issuer_name(client, clean)
        if not issuer:
            raise ValueError(f"NSEXBRL: could not resolve issuer name for {symbol}")

        filings = client.fetch_financials(clean, issuer, max_filings=NSE_XBRL_MAX_FILINGS)
        if not filings:
            raise ValueError(f"NSEXBRL: no parseable filings for {symbol}")

        # Prefer consolidated filings when both consolidated and standalone
        # are present for the same period; otherwise use whatever exists.
        consolidated = [f for f in filings if f.is_consolidated]
        chosen = consolidated if consolidated else filings
        chosen = sorted(chosen, key=lambda f: f.period_end or date.min, reverse=True)

        if not chosen:
            raise ValueError(f"NSEXBRL: no usable filings for {symbol}")

        latest = chosen[0]

        # ROE% uses trailing-4-quarter PAT over the latest reported equity —
        # NOT latest.ytd_pat, since ytd_pat alone would understate annualised
        # ROE whenever the latest filing happens to be a Q1 (only 1 quarter
        # of profit against a full year of equity in the denominator).
        ttm_pat = _ttm_sum(chosen, "q_pat")
        roe_pct = None
        if ttm_pat is not None and latest.bs_equity:
            roe_pct = round((ttm_pat / latest.bs_equity) * 100.0, 2)

        quarter_end = latest.period_end.isoformat() if latest.period_end else None
        as_of_date = (
            (latest.period_end + timedelta(days=NSE_XBRL_PIT_LAG_DAYS)).isoformat()
            if latest.period_end else None
        )

        debt_equity = latest.debt_equity_ratio
        book_value = latest.book_value_per_share

        return {
            "Symbol": symbol,
            "source": "nse_xbrl",

            # ── Capital structure — direct from the audited balance sheet
            "Debt_Equity": round(debt_equity, 3) if debt_equity is not None else None,
            "Book_Value": round(book_value, 2) if book_value is not None else None,
            "ROE%": roe_pct,

            # ── Growth — TTM only; see module docstring for why not 5Y/10Y
            "Sales_Growth_TTM%": _ttm_growth_pct(chosen, "q_revenue"),
            "EPS_Growth%": _ttm_growth_pct(chosen, "q_diluted_eps"),

            # ── PIT dates. Quarter_End is exact (from the filing itself);
            #    As_Of_Date is a conservative SEBI-lag estimate — see
            #    NSE_XBRL_PIT_LAG_DAYS docstring above.
            "Quarter_End": quarter_end,
            "As_Of_Date": as_of_date,
            "data_quality_flags": ["nse_xbrl_as_of_date_estimated"],

            # ── Provenance (useful for debugging / audit trail, not scored)
            "filing_consolidated": latest.is_consolidated,
            "filing_audited": latest.is_audited,
            "filing_seq_id": latest.seq_id,
        }

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        if not self.available:
            raise RuntimeError(
                "NSEXBRLProvider not available — missing NSE_COOKIE or nse-xbrl package"
            )
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._fetch_sync, symbol)
