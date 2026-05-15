# modules/adapters/yfinance.py
import asyncio
import logging
from typing import Any

import pandas as pd
import yfinance as yf

from modules.normalization.cleaner import _has_value, is_payload_skeletal

from .base import DataProvider

logger = logging.getLogger(__name__)


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

        return {
            "symbol": symbol,
            "Symbol": symbol,
            "source": self.name,
            "Price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "ROE%": (info.get("returnOnEquity") or 0) * 100,
            "Sales_Growth_5Y%": (info.get("revenueGrowth") or 0) * 100,
            "PE_Ratio": info.get("trailingPE"),
            "Debt_Equity": info.get("debtToEquity"),
            "F_Score": info.get("piotroskiScore"),
            "Sector": info.get("sector"),
            "pledge_percent": 0,
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf,
        }
