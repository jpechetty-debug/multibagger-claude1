# modules/adapters/yfinance.py
import asyncio
import math
from typing import Any

import pandas as pd
import yfinance as yf

from core.observability.logger import get_logger
from modules.normalization.cleaner import _has_value, is_payload_skeletal

from .base import DataProvider

logger = get_logger("adapters.yfinance")


def _finite(value: Any) -> float | None:
    """float(value) if it is a finite number, else None (yfinance uses None and NaN)."""
    if not _has_value(value):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _scaled(value: Any, factor: float) -> float | None:
    """value * factor, or None when yfinance has no usable number."""
    v = _finite(value)
    return None if v is None else round(v * factor, 4)


def _cfo_pat_ratio(cfo: Any, pat: Any) -> float | None:
    cfo_v, pat_v = _finite(cfo), _finite(pat)
    if cfo_v is None or pat_v is None or pat_v <= 0:
        return None
    return round(cfo_v / pat_v, 3)


async def _run_executor_safe(loop, executor, fn, default):
    try:
        return await loop.run_in_executor(executor, fn)
    except Exception as e:
        logger.debug(f"Executor Error in YFinanceProvider: {e}")
        return default


class YFinanceProvider(DataProvider):
    @property
    def name(self):
        return "yfinance"

    def __init__(self, executor):
        super().__init__()
        self.executor = executor

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        ticker = yf.Ticker(symbol)

        try:
            info = await _run_executor_safe(loop, self.executor, lambda: ticker.info, {})
        except AttributeError:
            info = {}

        if not isinstance(info, dict):
            info = {}

        if is_payload_skeletal({"info": info, "price": info.get("currentPrice")}, min_coverage=1):
            try:
                if hasattr(ticker, "fast_info"):
                    fast = await _run_executor_safe(
                        loop,
                        self.executor,
                        lambda: dict(ticker.fast_info) if ticker.fast_info is not None else {},
                        {},
                    )
                else:
                    fast = {}
            except (AttributeError, TypeError):
                fast = {}

            if isinstance(fast, dict) and fast:
                if not _has_value(info.get("currentPrice")) and _has_value(fast.get("lastPrice")):
                    info["currentPrice"] = fast.get("lastPrice")
                if not _has_value(info.get("marketCap")) and _has_value(fast.get("marketCap")):
                    info["marketCap"] = fast.get("marketCap")
                if not _has_value(info.get("fiftyTwoWeekHigh")) and _has_value(
                    fast.get("yearHigh")
                ):
                    info["fiftyTwoWeekHigh"] = fast.get("yearHigh")
                if not _has_value(info.get("fiftyTwoWeekLow")) and _has_value(fast.get("yearLow")):
                    info["fiftyTwoWeekLow"] = fast.get("yearLow")

        fin = await _run_executor_safe(
            loop,
            self.executor,
            lambda: getattr(ticker, "financials", pd.DataFrame()),
            pd.DataFrame(),
        )
        bs = await _run_executor_safe(
            loop,
            self.executor,
            lambda: getattr(ticker, "balance_sheet", pd.DataFrame()),
            pd.DataFrame(),
        )
        cf = await _run_executor_safe(
            loop,
            self.executor,
            lambda: getattr(ticker, "cash_flow", pd.DataFrame()),
            pd.DataFrame(),
        )

        # Missing stays None — the scorer reads 0 as a real (bad) value and caps on it.
        # yfinance units: returnOnEquity/revenueGrowth are fractions; debtToEquity is
        # always a percentage (10.2 means a 0.102 ratio).
        return {
            "symbol": symbol,
            "Symbol": symbol,
            "source": self.name,
            "Price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "ROE%": _scaled(info.get("returnOnEquity"), 100),
            "Sales_Growth_TTM%": _scaled(info.get("revenueGrowth"), 100),
            "PE_Ratio": info.get("trailingPE"),
            "Debt_Equity": _scaled(info.get("debtToEquity"), 0.01),
            "CFO_PAT_Ratio": _cfo_pat_ratio(info.get("operatingCashflow"), info.get("netIncomeToCommon")),
            "F_Score": info.get("piotroskiScore"),
            "Sector": info.get("sector"),
            "pledge_percent": 0,
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf,
        }
