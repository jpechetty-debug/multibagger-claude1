# modules/adapters/nse.py
import asyncio
from core.observability.logger import get_logger
from typing import Any

try:
    import curl_cffi.requests as requests
    if not hasattr(requests, "RequestException"):
        import curl_cffi.requests.exceptions as exceptions
        requests.RequestException = exceptions.RequestException  # type: ignore
except ImportError:
    pass

import pandas as pd
import yfinance as yf

from modules.normalization.cleaner import normalize_info

from .base import DataProvider

logger = get_logger("adapters.nse")


async def _run_executor_safe(loop, executor, fn, default):
    try:
        return await loop.run_in_executor(executor, fn)
    except Exception as e:
        logger.debug(f"Executor Error in NSEProvider: {e}")
        return default


_PNSEA_INFO_ALIASES: dict[str, tuple[str, ...]] = {
    # Priority order: most-specific Indian source key first, generic yfinance-style last.
    # When multiple keys are found with non-None values, resolve_key picks [0] and logs
    # a "key_conflict" warning so conflicts are visible and can be monitored.
    "marketCap":      ("marketCap", "marketCapTotal", "marketCapitalization"),
    "trailingPE":     ("trailingPE", "pe", "pE"),
    "returnOnEquity": ("returnOnEquity", "roe"),
    "debtToEquity":   ("debtToEquity", "debtEquity"),
    # revenueGrowth vs salesGrowth: these have different semantics in Indian data.
    # salesGrowth is NSE-reported YoY; revenueGrowth may include other income.
    # NSE salesGrowth is preferred — change order here if source semantics differ.
    "revenueGrowth":  ("salesGrowth", "revenueGrowth"),
    "earningsGrowth": ("profitGrowth", "earningsGrowth"),
    "bookValue":      ("bookValue",),
    "trailingEps":    ("eps", "trailingEps"),
    "fiftyTwoWeekHigh": ("fiftyTwoWeekHigh", "weekHigh52"),
    "fiftyTwoWeekLow":  ("fiftyTwoWeekLow", "weekLow52"),
    # sector from NSE is authoritative for Indian stocks — prefer over yfinance
    "sector":   ("sectorName", "sector"),
    "industry": ("industryName", "industry"),
}

_NSEPYTHON_INFO_ALIASES: dict[str, tuple[str, ...]] = {
    "marketCap":      ("marketCap", "marketCapitalization"),
    "trailingPE":     ("pe", "peRatio", "trailingPE"),
    "returnOnEquity": ("roe", "returnOnEquity"),
    "debtToEquity":   ("debtEquity", "deRatio", "debtToEquity"),
    "revenueGrowth":  ("salesGrowth", "revenueGrowth"),
    "earningsGrowth": ("epsGrowth", "profitGrowth", "earningsGrowth"),
    "bookValue":      ("bookValue",),
    "trailingEps":    ("eps", "trailingEps"),
    "fiftyTwoWeekHigh": ("high52Week", "fiftyTwoWeekHigh"),
    "fiftyTwoWeekLow":  ("low52Week", "fiftyTwoWeekLow"),
    "sector":   ("sector",),
    "industry": ("industry",),
}


class PNSEAProvider(DataProvider):
    @property
    def name(self):
        return "pnsea"

    def __init__(self, executor, nse_factory=None):
        super().__init__()
        self.executor = executor
        self.nse = None
        self._nse_factory = nse_factory
        try:
            if self._nse_factory is None:
                from pnsea import NSE

                self._nse_factory = NSE
            self.available = True
        except ImportError:
            self.available = False
        except Exception as exc:
            logger.warning(f"PNSEA bootstrap failed during import; provider disabled: {exc}")
            self.available = False

    def _get_nse_client(self):
        if self.nse is None:
            if self._nse_factory is None:
                raise ImportError("PNSEA not available")
            self.nse = self._nse_factory()
        return self.nse

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        if not self.available:
            raise ImportError("PNSEA not available")
        loop = asyncio.get_running_loop()
        nse_client = await loop.run_in_executor(self.executor, self._get_nse_client)
        raw = await loop.run_in_executor(
            self.executor, lambda: nse_client.equity.info(symbol.replace(".NS", ""))
        )
        pledged = await _run_executor_safe(
            loop,
            self.executor,
            lambda: nse_client.insider.getPledgedData(symbol.replace(".NS", "")),
            {},
        )

        yf_t = yf.Ticker(symbol)
        fin = await _run_executor_safe(
            loop, self.executor, lambda: getattr(yf_t, "financials", pd.DataFrame()), pd.DataFrame()
        )
        bs = await _run_executor_safe(
            loop,
            self.executor,
            lambda: getattr(yf_t, "balance_sheet", pd.DataFrame()),
            pd.DataFrame(),
        )
        cf = await _run_executor_safe(
            loop, self.executor, lambda: getattr(yf_t, "cash_flow", pd.DataFrame()), pd.DataFrame()
        )
        raw_info = raw.get("info", {})
        raw_info["_source"] = self.name   # enables resolve_key conflict logging
        info = normalize_info(raw_info, alias_map=_PNSEA_INFO_ALIASES)

        cfo_pat = 0.0
        try:
            cfo_pat = raw.get("info", {}).get("cashFlowFromOperations", 0) / max(
                raw.get("info", {}).get("netProfit", 1), 1
            )
        except (ZeroDivisionError, TypeError, ValueError) as _cfo_err:
            logger.warning(f"[{symbol}] CFO/PAT ratio calculation failed: {_cfo_err}")

        return {
            "symbol": symbol,
            "source": self.name,
            "price": raw.get("priceInfo", {}).get("lastPrice"),
            "roe": raw.get("info", {}).get("roe"),
            "sales_growth": raw.get("info", {}).get("salesGrowth"),
            "cfo_pat": cfo_pat,
            "pledge_percent": pledged.get("pledgedPercentage", 0)
            if isinstance(pledged, dict)
            else 0,
            "promoter_holding": raw.get("info", {}).get("promoterHolding"),
            "fii_dii": {
                "fii": raw.get("info", {}).get("fiiHolding"),
                "dii": raw.get("info", {}).get("diiHolding"),
            },
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf,
        }


class NSEPythonProvider(DataProvider):
    @property
    def name(self):
        return "nsepython"

    def __init__(self, executor):
        super().__init__()
        self.executor = executor
        try:
            from nsepython import (
                get_bulk_deals,
                get_fundamentals,
                get_pledged_shares,
                get_quote,
                get_shareholding,
            )

            self.api_quote = get_quote
            self.api_fundamentals = get_fundamentals
            self.api_bulk = get_bulk_deals
            self.api_pledged = get_pledged_shares
            self.api_share = get_shareholding
            self.available = True
        except ImportError:
            self.available = False

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        if not self.available:
            raise ImportError("nsepython not available")
        loop = asyncio.get_running_loop()
        sym = symbol.replace(".NS", "")

        quote = await loop.run_in_executor(self.executor, self.api_quote, sym)
        fundamentals = await loop.run_in_executor(self.executor, self.api_fundamentals, sym)
        pledged = await _run_executor_safe(loop, self.executor, lambda: self.api_pledged(sym), {})
        bulk = await _run_executor_safe(loop, self.executor, lambda: self.api_bulk(sym), [])
        shareholding = await _run_executor_safe(
            loop, self.executor, lambda: self.api_share(sym), {}
        )

        yf_t = yf.Ticker(symbol)
        fin = await _run_executor_safe(
            loop, self.executor, lambda: getattr(yf_t, "financials", pd.DataFrame()), pd.DataFrame()
        )
        bs = await _run_executor_safe(
            loop,
            self.executor,
            lambda: getattr(yf_t, "balance_sheet", pd.DataFrame()),
            pd.DataFrame(),
        )
        cf = await _run_executor_safe(
            loop, self.executor, lambda: getattr(yf_t, "cash_flow", pd.DataFrame()), pd.DataFrame()
        )
        fundamentals["_source"] = self.name  # enables resolve_key conflict logging
        info = normalize_info(fundamentals, alias_map=_NSEPYTHON_INFO_ALIASES)

        return {
            "symbol": symbol,
            "source": self.name,
            "price": quote.get("priceInfo", {}).get("lastPrice"),
            "roe": fundamentals.get("roe"),
            "sales_growth": fundamentals.get("salesGrowth"),
            "cfo_pat": fundamentals.get("cfoPatRatio", 0),
            "pledge_percent": pledged.get("pledgePercent", 0),
            "promoter_holding": shareholding.get("promoter", 0),
            "fii_dii": shareholding.get("institutional", {}),
            "bulk_deals": bulk,
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf,
        }
