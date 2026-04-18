
# Consolidated DataService containing logic from data_loader, market, market_data, and data_manager.
# modules/data_manager.py
# Sovereign AI - Production Data Manager
# Fully upgraded Data Pipeline: Abstract DataProvider, SQLite Cache, Tenacity Retries, Data Quality filters.

import asyncio
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
from typing import Dict, List, Optional, Any
import logging
import sqlite3
import pickle
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, date, timedelta

import pandas_market_calendars as mcal
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from modules.sources.groww_source import GrowwSource
from modules.sources.nse_source import NSESource
from modules.sources.yfinance_source import YFinanceSource

logger = logging.getLogger(__name__)

_FUNDAMENTAL_KEYS = (
    "marketCap",
    "trailingPE",
    "returnOnEquity",
    "debtToEquity",
    "revenueGrowth",
    "earningsGrowth",
    "sector",
    "industry",
)

_TRANSIENT_ERROR_HINTS = (
    "timeout",
    "timed out",
    "429",
    "rate limit",
    "too many requests",
    "temporarily unavailable",
    "connection reset",
    "ssl",
    "name resolution",
)


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _normalize_info(
    primary_info: Optional[Dict[str, Any]],
    *,
    fallback_info: Optional[Dict[str, Any]] = None,
    alias_map: Optional[Dict[str, tuple]] = None,
) -> Dict[str, Any]:
    """Build canonical info dict using provider payload + yfinance fallback."""
    normalized: Dict[str, Any] = {}
    if isinstance(fallback_info, dict):
        for key, value in fallback_info.items():
            if _has_value(value):
                normalized[key] = value
    if isinstance(primary_info, dict):
        for key, value in primary_info.items():
            if _has_value(value):
                normalized[key] = value
    if alias_map and isinstance(primary_info, dict):
        for target, aliases in alias_map.items():
            if _has_value(normalized.get(target)):
                continue
            for alias in aliases:
                candidate = primary_info.get(alias)
                if _has_value(candidate):
                    normalized[target] = candidate
                    break
    return normalized


def _is_missing_or_zero(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"", "none", "nan", "na", "null", "0", "0.0"}
    try:
        num = float(value)
        return num == 0.0
    except Exception:
        return False


def _fundamental_coverage(info: Any) -> int:
    if not isinstance(info, dict):
        return 0
    covered = 0
    for key in _FUNDAMENTAL_KEYS:
        value = info.get(key)
        if key in {"marketCap", "trailingPE"}:
            if _is_missing_or_zero(value):
                continue
        elif not _has_value(value):
            continue
        covered += 1
    return covered


def _is_payload_skeletal(payload: Any, *, min_coverage: int = 3) -> bool:
    if not isinstance(payload, dict):
        return True
    
    # Critical Hardening: Any payload missing a valid, non-zero price is skeletal
    price = payload.get("price")
    if price is None:
        return True
    
    try:
        price_val = float(price)
        if price_val <= 0:
            return True
    except (ValueError, TypeError):
        return True

    info = payload.get("info", {})
    if not isinstance(info, dict) or not info:
        return True

    # Strict Fundamental Requirement: Market Cap and Sector must exist
    if _is_missing_or_zero(info.get("marketCap")) or not _has_value(info.get("sector")):
        return True

    coverage = _fundamental_coverage(info)
    return coverage < int(min_coverage)


async def _run_executor_safe(loop, executor, fn, default):
    try:
        return await loop.run_in_executor(executor, fn)
    except Exception as e:
        logger.debug(f"Executor Error in DataManager: {e}")
        return default


def _run_coroutine_sync(coro):
    """Run an async coroutine from synchronous compatibility wrappers."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result = {}
    error = {}

    def _runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - passthrough for sync callers
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result.get("value")


_PNSEA_INFO_ALIASES = {
    "marketCap": ("marketCap", "marketCapTotal", "marketCapitalization"),
    "trailingPE": ("trailingPE", "pe", "pE"),
    "returnOnEquity": ("returnOnEquity", "roe"),
    "debtToEquity": ("debtToEquity", "debtEquity"),
    "revenueGrowth": ("revenueGrowth", "salesGrowth"),
    "earningsGrowth": ("earningsGrowth", "profitGrowth"),
    "bookValue": ("bookValue",),
    "trailingEps": ("trailingEps", "eps"),
    "fiftyTwoWeekHigh": ("fiftyTwoWeekHigh", "weekHigh52"),
    "fiftyTwoWeekLow": ("fiftyTwoWeekLow", "weekLow52"),
    "sector": ("sector", "sectorName"),
    "industry": ("industry", "industryName"),
}

_NSEPYTHON_INFO_ALIASES = {
    "marketCap": ("marketCap", "marketCapitalization"),
    "trailingPE": ("trailingPE", "pe", "peRatio"),
    "returnOnEquity": ("returnOnEquity", "roe"),
    "debtToEquity": ("debtToEquity", "debtEquity", "deRatio"),
    "revenueGrowth": ("revenueGrowth", "salesGrowth"),
    "earningsGrowth": ("earningsGrowth", "profitGrowth", "epsGrowth"),
    "bookValue": ("bookValue",),
    "trailingEps": ("trailingEps", "eps"),
    "fiftyTwoWeekHigh": ("fiftyTwoWeekHigh", "high52Week"),
    "fiftyTwoWeekLow": ("fiftyTwoWeekLow", "low52Week"),
    "sector": ("sector",),
    "industry": ("industry",),
}

# --- Dynamic Market Calendar ---
def get_valid_trading_days(start_date, end_date):
    nse = mcal.get_calendar('NSE')
    schedule = nse.schedule(start_date=start_date, end_date=end_date)
    return schedule.index.date

# --- Persistent Caching (Pickle + SQLite) ---
class PersistentCache:
    def __init__(self, db_path="data_cache.db", ttl_seconds=86400):
        self.db_path = db_path
        self.ttl = ttl_seconds
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS cache
                            (key TEXT PRIMARY KEY, value BLOB, timestamp REAL)''')
            conn.commit()

    def get_expired(self, key: str) -> Optional[Any]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    return pickle.loads(row[0])
        except Exception as e:
            logger.warning(f"Expired Cache read error for {key}: {e}")
            return None

    def get(self, key: str) -> Optional[Any]:
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value, timestamp FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    val, ts = row
                    if time.time() - ts < self.ttl:
                        return pickle.loads(val)
                    else:
                        cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
            return None
        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
            return None

    def set(self, key: str, value: Any):
        try:
            with sqlite3.connect(self.db_path, timeout=5) as conn:
                conn.execute("INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
                             (key, pickle.dumps(value), time.time()))
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache write error for {key}: {e}")

# --- Abstract Data Provider ---
class DataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def fetch_fundamentals(self, symbol: str) -> Dict:
        pass

# --- Concrete Providers ---
class PNSEAProvider(DataProvider):
    @property
    def name(self): return "pnsea"
    
    def __init__(self, executor, nse_factory=None):
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
            logger.warning("PNSEA bootstrap failed during import; provider disabled: %s", exc)
            self.available = False

    def _get_nse_client(self):
        if self.nse is None:
            if self._nse_factory is None:
                raise ImportError("PNSEA not available")
            self.nse = self._nse_factory()
        return self.nse

    async def fetch_fundamentals(self, symbol: str) -> Dict:
        if not self.available:
            raise ImportError("PNSEA not available")
        loop = asyncio.get_running_loop()
        nse_client = await loop.run_in_executor(self.executor, self._get_nse_client)
        raw = await loop.run_in_executor(self.executor, lambda: nse_client.equity.info(symbol.replace(".NS", "")))
        pledged = await _run_executor_safe(
            loop,
            self.executor,
            lambda: nse_client.insider.getPledgedData(symbol.replace(".NS", "")),
            {},
        )

        yf_t = yf.Ticker(symbol)
        fin = await _run_executor_safe(loop, self.executor, lambda: getattr(yf_t, "financials", pd.DataFrame()), pd.DataFrame())
        bs = await _run_executor_safe(loop, self.executor, lambda: getattr(yf_t, "balance_sheet", pd.DataFrame()), pd.DataFrame())
        cf = await _run_executor_safe(loop, self.executor, lambda: getattr(yf_t, "cash_flow", pd.DataFrame()), pd.DataFrame())
        info = _normalize_info(raw.get("info", {}), alias_map=_PNSEA_INFO_ALIASES)

        cfo_pat = 0.0
        try:
            cfo_pat = raw.get("info", {}).get("cashFlowFromOperations", 0) / max(raw.get("info", {}).get("netProfit", 1), 1)
        except (ZeroDivisionError, TypeError, ValueError) as _cfo_err:
            logger.warning("[%s] CFO/PAT ratio calculation failed: %s", symbol, _cfo_err)

        return {
            "symbol": symbol,
            "source": self.name,
            "price": raw.get("priceInfo", {}).get("lastPrice"),
            "roe": raw.get("info", {}).get("roe"),
            "sales_growth": raw.get("info", {}).get("salesGrowth"),
            "cfo_pat": cfo_pat,
            "pledge_percent": pledged.get("pledgedPercentage", 0) if isinstance(pledged, dict) else 0,
            "promoter_holding": raw.get("info", {}).get("promoterHolding"),
            "fii_dii": {
                "fii": raw.get("info", {}).get("fiiHolding"),
                "dii": raw.get("info", {}).get("diiHolding")
            },
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf
        }

class NSEPythonProvider(DataProvider):
    @property
    def name(self): return "nsepython"
    
    def __init__(self, executor):
        self.executor = executor
        try:
            from nsepython import get_quote, get_fundamentals, get_bulk_deals, get_pledged_shares, get_shareholding
            self.api_quote = get_quote
            self.api_fundamentals = get_fundamentals
            self.api_bulk = get_bulk_deals
            self.api_pledged = get_pledged_shares
            self.api_share = get_shareholding
            self.available = True
        except ImportError:
            self.available = False

    async def fetch_fundamentals(self, symbol: str) -> Dict:
        if not self.available:
            raise ImportError("nsepython not available")
        loop = asyncio.get_running_loop()
        sym = symbol.replace(".NS", "")
        
        quote = await loop.run_in_executor(self.executor, self.api_quote, sym)
        fundamentals = await loop.run_in_executor(self.executor, self.api_fundamentals, sym)
        pledged = await _run_executor_safe(loop, self.executor, lambda: self.api_pledged(sym), {})
        bulk = await _run_executor_safe(loop, self.executor, lambda: self.api_bulk(sym), [])
        shareholding = await _run_executor_safe(loop, self.executor, lambda: self.api_share(sym), {})

        yf_t = yf.Ticker(symbol)
        fin = await _run_executor_safe(loop, self.executor, lambda: getattr(yf_t, "financials", pd.DataFrame()), pd.DataFrame())
        bs = await _run_executor_safe(loop, self.executor, lambda: getattr(yf_t, "balance_sheet", pd.DataFrame()), pd.DataFrame())
        cf = await _run_executor_safe(loop, self.executor, lambda: getattr(yf_t, "cash_flow", pd.DataFrame()), pd.DataFrame())
        info = _normalize_info(fundamentals, alias_map=_NSEPYTHON_INFO_ALIASES)

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
            "cash_flow": cf
        }

class YFinanceProvider(DataProvider):
    @property
    def name(self): return "yfinance"

    def __init__(self, executor):
        self.executor = executor
        self.available = True

    async def fetch_fundamentals(self, symbol: str) -> Dict:
        loop = asyncio.get_running_loop()
        ticker = yf.Ticker(symbol)
        
        # Robust attribute access for ticker.info
        try:
            info = await _run_executor_safe(loop, self.executor, lambda: ticker.info, {})
        except AttributeError:
            info = {}
            
        if not isinstance(info, dict):
            info = {}
            
        if _is_payload_skeletal({"info": info, "price": info.get("currentPrice")}, min_coverage=1):
            # Safe attribute access for fast_info which may be missing in older yfinance versions
            try:
                if hasattr(ticker, "fast_info"):
                    fast = await _run_executor_safe(loop, self.executor, 
                        lambda: dict(ticker.fast_info) if ticker.fast_info is not None else {}, {})
                else:
                    fast = {}
            except (AttributeError, TypeError):
                fast = {}
                
            if isinstance(fast, dict) and fast:
                if not _has_value(info.get("currentPrice")) and _has_value(fast.get("lastPrice")):
                    info["currentPrice"] = fast.get("lastPrice")
                if not _has_value(info.get("marketCap")) and _has_value(fast.get("marketCap")):
                    info["marketCap"] = fast.get("marketCap")
                if not _has_value(info.get("fiftyTwoWeekHigh")) and _has_value(fast.get("yearHigh")):
                    info["fiftyTwoWeekHigh"] = fast.get("yearHigh")
                if not _has_value(info.get("fiftyTwoWeekLow")) and _has_value(fast.get("yearLow")):
                    info["fiftyTwoWeekLow"] = fast.get("yearLow")
        
        # Financials access hardening
        fin = await _run_executor_safe(loop, self.executor, lambda: getattr(ticker, "financials", pd.DataFrame()), pd.DataFrame())
        bs = await _run_executor_safe(loop, self.executor, lambda: getattr(ticker, "balance_sheet", pd.DataFrame()), pd.DataFrame())
        cf = await _run_executor_safe(loop, self.executor, lambda: getattr(ticker, "cash_flow", pd.DataFrame()), pd.DataFrame())
        
        return {
            "symbol": symbol,
            "source": self.name,
            "price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "roe": info.get("returnOnEquity"),
            "sales_growth": info.get("revenueGrowth"),
            "pledge_percent": 0,
            "info": info,
            "financials": fin,
            "balance_sheet": bs,
            "cash_flow": cf
        }

# --- Legacy Compatibility Manager ---
class DataSourceManager:
    """
    Backward-compatible synchronous manager used by older modules and tests.

    The newer async-first production path uses ``DataManager`` below. This
    compatibility layer preserves the legacy fallback chain that wraps the
    ``modules.sources`` adapters.
    """

    def __init__(self, sources: Optional[List[Any]] = None):
        self.sources = list(sources or [YFinanceSource(), NSESource(), GrowwSource()])

    def fetch_fundamentals(self, symbol: str) -> Dict:
        for source in self.sources:
            try:
                data = source.fetch_fundamentals(symbol)
                if data and "error" not in data:
                    return data
            except Exception as exc:
                logger.warning(
                    "Legacy source %s failed for %s: %s",
                    source.__class__.__name__,
                    symbol,
                    exc,
                )
        return {"symbol": symbol, "error": "All sources failed"}

    def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        for source in self.sources:
            try:
                history = source.fetch_history(symbol, period=period)
                if history is not None and not history.empty:
                    return history
            except Exception as exc:
                logger.warning(
                    "Legacy history source %s failed for %s: %s",
                    source.__class__.__name__,
                    symbol,
                    exc,
                )
        return pd.DataFrame()

    def fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        for source in self.sources:
            try:
                timeline = source.fetch_quarterly_results(symbol)
                if timeline:
                    return timeline
            except Exception as exc:
                logger.warning(
                    "Legacy quarterly source %s failed for %s: %s",
                    source.__class__.__name__,
                    symbol,
                    exc,
                )
        return []


# --- Main Data Manager ---
class DataManager:
    def __init__(self, max_concurrency: int = 15):
        self.max_concurrency = int(max_concurrency)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self.provider_timeout_seconds = 3 # Optimized from 4
        self.yfinance_timeout_seconds = 8 # Optimized from 10
        self.history_timeout_seconds = 6 # Optimized from 8
        self.provider_fail_streak = {}
        self.provider_cooldown_until = {}
        
        # Priority Fallback List
        self.providers = [
            PNSEAProvider(self.executor),
            NSEPythonProvider(self.executor),
            YFinanceProvider(self.executor)
        ]
        
        # Persistent Cache (TTL: 24h for fundamentals, 1h for fast data)
        self.cache = PersistentCache()
        
        current_year = datetime.now().year
        self.valid_trading_days = get_valid_trading_days(f'{current_year-10}-01-01', f'{current_year+2}-12-31')

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    def _is_transient_error(self, exc: Exception) -> bool:
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
            return True
        text = str(exc).lower()
        return any(hint in text for hint in _TRANSIENT_ERROR_HINTS)

    def _record_provider_success(self, provider_name: str):
        self.provider_fail_streak[provider_name] = 0
        self.provider_cooldown_until.pop(provider_name, None)

    def _record_provider_failure(self, provider_name: str, *, transient: bool):
        streak = int(self.provider_fail_streak.get(provider_name, 0)) + 1
        self.provider_fail_streak[provider_name] = streak
        if transient and streak >= 4:
            cooldown = min(30, streak * 2)
            self.provider_cooldown_until[provider_name] = time.time() + cooldown

    async def _adaptive_pause(self, provider_name: str):
        streak = int(self.provider_fail_streak.get(provider_name, 0))
        if streak <= 1:
            return
        pause_seconds = min(2.5, 0.2 * streak)
        await asyncio.sleep(pause_seconds)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asyncio.TimeoutError, TimeoutError)),
    )
    async def async_fetch_fundamentals(self, symbol: str) -> Dict:
        """Main entry point - returns normalized dict with 12-point checklist data"""
        async with self.semaphore:
            cache_key = f"fund_{symbol}"
            cached = self.cache.get(cache_key)
            if cached:
                cached['data_freshness'] = 'live (cached within TTL)'
                return cached

            incomplete_payload = None

            # Try providers in priority order
            for provider in self.providers:
                if not getattr(provider, 'available', True):
                    continue
                provider_name = provider.name
                if self.provider_cooldown_until.get(provider_name, 0) > time.time():
                    continue
                try:
                    timeout_s = self.yfinance_timeout_seconds if provider_name == "yfinance" else self.provider_timeout_seconds
                    data = await asyncio.wait_for(provider.fetch_fundamentals(symbol), timeout=timeout_s)
                    if data and "error" not in data:
                        if _is_payload_skeletal(data):
                            incomplete_payload = data
                            if provider_name != "yfinance":
                                self._record_provider_failure(provider_name, transient=False)
                                continue
                        data['data_freshness'] = 'live'
                        self.cache.set(cache_key, data)
                        self._record_provider_success(provider_name)
                        return data
                except Exception as e:
                    transient = self._is_transient_error(e)
                    self._record_provider_failure(provider_name, transient=transient)
                    if transient:
                        await self._adaptive_pause(provider_name)
                    logger.warning(f"Provider {provider.name} failed for {symbol}: {e}")
                    continue

            if incomplete_payload:
                incomplete_payload['data_freshness'] = 'stale (incomplete fallback)'
                return incomplete_payload
            
            # Fallback to expired cache if available to prevent catastrophic failure
            stale_cached = self.cache.get_expired(cache_key)
            if stale_cached:
                stale_cached['data_freshness'] = 'stale (beyond TTL)'
                stale_cached['error'] = 'All providers failed, returning stale cache'
                return stale_cached
            
            return {"symbol": symbol, "error": "All providers failed", "data_freshness": "stale (no cache)", "source": "fallback_failed"}

    def fetch_fundamentals(self, symbol: str) -> Dict:
        """Synchronous compatibility wrapper for older callers."""
        return _run_coroutine_sync(self.async_fetch_fundamentals(symbol))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
    async def async_fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Fetch historical price data with quality checks"""
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            ticker = yf.Ticker(symbol)
            df = pd.DataFrame()
            for attempt in range(2):
                try:
                    df = await asyncio.wait_for(
                        loop.run_in_executor(self.executor, lambda: ticker.history(period=period)),
                        timeout=self.history_timeout_seconds,
                    )
                except Exception as exc:
                    if attempt == 0 and self._is_transient_error(exc):
                        await asyncio.sleep(0.6)
                        continue
                    raise
                if df.empty or 'Close' not in df.columns:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    return pd.DataFrame()
                break
            
            if df.empty or 'Close' not in df.columns:
                return pd.DataFrame()
                
            # --- Data Quality Checks ---
            # 1. Price Continuity (Remove extreme spikes > 50% in one day unless penny stock)
            pct_change = df['Close'].pct_change().abs()
            glitch_mask = (df['Close'] > 10) & (pct_change > 0.5)
            if glitch_mask.any():
                logger.warning(f"[{symbol}] Data glitch detected: price jump > 50%. Ignoring anomalies.")
                df = df[~glitch_mask]
                
            # 2. Volume Sanity check
            if 'Volume' in df.columns:
                df.loc[df['Volume'] < 0, 'Volume'] = 0
            
            # --- MARKET CLOSED FIX (Dynamic) ---
            today = datetime.now().date()
            is_valid_trading_day = today in self.valid_trading_days
            is_holiday_or_weekend = not is_valid_trading_day
            
            df = df.dropna(subset=['Close'])
            if len(df) >= 2 and 'Volume' in df.columns and (pd.isna(df['Volume'].iloc[-1]) or df['Volume'].iloc[-1] == 0 or is_holiday_or_weekend):
                df = df.iloc[:-1]
                
            return df

    def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """Synchronous compatibility wrapper for older callers."""
        return _run_coroutine_sync(self.async_fetch_history(symbol, period=period))

    async def async_fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        """Fetch quarterly financial results"""
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            ticker = yf.Ticker(symbol)
            qf = await loop.run_in_executor(self.executor, lambda: ticker.quarterly_financials)
            if qf.empty: return []
            
            results = []
            for col in qf.columns:
                results.append({
                    "date": col.strftime('%Y-%m-%d') if hasattr(col, 'strftime') else str(col),
                    "revenue": qf.loc["Total Revenue", col] if "Total Revenue" in qf.index else 0,
                    "profit": qf.loc["Net Income", col] if "Net Income" in qf.index else 0
                })
            return results

    def fetch_quarterly_results(self, symbol: str) -> List[Dict]:
        """Synchronous compatibility wrapper for older callers."""
        return _run_coroutine_sync(self.async_fetch_quarterly_results(symbol))

    async def fetch_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        tasks = [self.async_fetch_fundamentals(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {sym: res for sym, res in zip(symbols, results) if not isinstance(res, Exception)}

    async def close(self):
        self.executor.shutdown(wait=True)

# For backward compatibility singleton
data_manager = DataManager()


# --- FROM data_loader.py ---
import pandas as pd
import os

def load_tickers_from_csv(file_paths):
    """
    Reads multiple CSV files, extracts symbols, deduplicates, and formats them for yfinance (.NS).
    """
    all_symbols = set()
    
    for file_path in file_paths:
        if not os.path.exists(file_path):
            print(f"Warning: File not found: {file_path}")
            continue
            
        try:
            # key is usually "SYMBOL" or "Symbol"
            # Some NSE CSVs have garbage in first few lines or trailing whitespace
            df = pd.read_csv(file_path)
            
            # Clean column names (strip whitespace)
            df.columns = df.columns.str.strip()
            
            # Find symbol column
            symbol_col = None
            for col in ["SYMBOL", "Symbol", "Ticker", "ISIN"]:
                if col in df.columns:
                    symbol_col = col
                    break
            
            if symbol_col:
                symbols = df[symbol_col].dropna().unique()
                for sym in symbols:
                    sym = str(sym).strip()
                    if not sym.endswith(".NS") and not sym.endswith(".BO"):
                        sym += ".NS"
                    all_symbols.add(sym)
            else:
                print(f"Warning: No 'SYMBOL' column found in {file_path}")
                
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            
    return list(all_symbols)


# --- FROM market.py ---
import yfinance as yf

def analyze_market_regime(symbol="^NSEI"):
    """
    Determines Market Regime: Bull, Bear, Correction, Sideways.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y") # Need 200 DMA
        
        if len(hist) < 200:
            return "Unknown"
            
        sma_50 = hist['Close'].tail(50).mean()
        sma_200 = hist['Close'].tail(200).mean()
        current_price = hist['Close'].iloc[-1]
        
        if current_price > sma_50 and sma_50 > sma_200:
            return "Bull Market"
        elif current_price < sma_50 and sma_50 < sma_200:
            return "Bear Market"
        elif current_price < sma_50 and current_price > sma_200:
            return "Correction"
        elif current_price > sma_50 and current_price < sma_200:
            return "Recovery"
        else:
            return "Sideways"
    except:
        return "Unknown"

def analyze_sector_rotation(stock_list):
    sector_returns = {}
    sector_counts = {}
    
    print("\nCalculating Sector Rotation...")
    for stock in stock_list:
        sec = stock.get("Sector", "Unknown")
        rs = stock.get("RS_Rating", 0)
        
        if sec not in sector_returns:
            sector_returns[sec] = 0.0
            sector_counts[sec] = 0
        
        sector_returns[sec] += rs
        sector_counts[sec] += 1
        
    avg_sector_rs = {}
    for sec, total_rs in sector_returns.items():
        if sector_counts[sec] > 0:
            avg_sector_rs[sec] = total_rs / sector_counts[sec]
            
    sorted_sectors = sorted(avg_sector_rs.items(), key=lambda x: x[1], reverse=True)
    
    print("Top 3 Leading Sectors (by RS):")
    top_3 = []
    for i, (sec, rs) in enumerate(sorted_sectors[:3]):
        print(f"{i+1}. {sec}: Avg RS {rs:.2f}")
        top_3.append(sec)
        
    return top_3


# --- FROM market_data.py ---
import yfinance as yf
import pandas as pd
import logging
from modules.regime_hmm import RegimeHMM

logger = logging.getLogger(__name__)

class MarketDataProvider:
    """
    Fetches market data for macro-risk analysis.
    """
    
    def __init__(self):
        self.vix_ticker = "^INDIAVIX" # or "^VIX" if US, but assuming India based on context
        
    def get_vix_threshold(self, lookback_days=365, percentile=0.75):
        """
        Fetches historical VIX and calculates the dynamic high-stress threshold.
        
        Args:
            lookback_days (int): History to analyze (default 1 year).
            percentile (float): Percentile defining 'High Stress' (default 75th).
            
        Returns:
            float: The VIX threshold (e.g., 18.5).
        """
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days + 10) # Buffer
            
            # Fetch Data
            # Note: yfinance might fail on some corporate firewalls or if ticker invalid.
            # We add a fallback just in case.
            data = yf.download(self.vix_ticker, start=start_date, end=end_date, progress=False)
            
            if data.empty:
                print(f"⚠️ Warning: Could not fetch VIX data for {self.vix_ticker}. Using Fallback.")
                return 30.0 # Standard fallback
                
            # Calculate Percentile
            # 'Close' column might be multi-level if yf download structure changes, ensuring robust access.
            if isinstance(data.columns, pd.MultiIndex):
                vix_series = data[('Close', self.vix_ticker)]
            else:
                vix_series = data['Close']
                
            threshold = vix_series.quantile(percentile)
            current_vix = vix_series.iloc[-1]
            
            print(f"--- Market Regime: VIX 75th Percentile = {threshold:.2f} (Current: {current_vix:.2f}) ---")
            return float(threshold), float(current_vix)
            
        except Exception as e:
            logger.warning("Market data: VIX fetch failed: %s", e)
            return 30.0, 0.0

    def get_market_breadth(self):
        """
        Calculates Market Breadth using Nifty 50 constituents.
        Proxy: Ratio of stocks trading above their 50-day SMA.
        Returns:
            float: Breadth Ratio (0.0 to 1.0)
            int: Count of stocks > SMA50
        """
        # Representative Nifty 50 List (Top Weights)
        nifty_50_tickers = [
            "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS", 
            "BHARTIARTL.NS", "ITC.NS", "SBIN.NS", "LICI.NS", "HINDUNILVR.NS",
            "LT.NS", "BAJFINANCE.NS", "MARUTI.NS", "HCLTECH.NS", "SUNPHARMA.NS",
            "TATAMOTORS.NS", "ULTRACEMCO.NS", "AXISBANK.NS", "NTPC.NS", "TITAN.NS",
            "ADANIENT.NS", "ONGC.NS", "KOTAKBANK.NS", "POWERGRID.NS", "WIPRO.NS",
            "M&M.NS", "BAJAJFINSV.NS", "COALINDIA.NS", "ASIANPAINT.NS", "JSWSTEEL.NS"
        ] # Top 30 is sufficient proxy
        
        try:
            print("--- Checking Market Breadth (Nifty 30 Proxy) ---")
            data = self.get_batch_history(nifty_50_tickers, period="3mo")
            if data.empty:
                return 0.5, 15 # Neutral fallback
            
            above_sma = 0
            valid_tickers = 0
            
            # Calculate SMA50 for each
            for ticker in data.columns:
                series = data[ticker].dropna()
                if len(series) > 50:
                    sma50 = series.rolling(window=50).mean().iloc[-1]
                    current = series.iloc[-1]
                    if current > sma50:
                        above_sma += 1
                    valid_tickers += 1
            
            if valid_tickers == 0:
                return 0.5, 0
                
            ratio = above_sma / valid_tickers
            print(f"   [INFO] Breadth: {above_sma}/{valid_tickers} ({ratio:.1%}) stocks > SMA50")
            return ratio, above_sma
            
        except Exception as e:
            logger.warning("Market data: breadth calculation failed: %s", e)
            return 0.5, 0

    def get_market_regime(self, index_ticker="^NSEI"):
        """
        Determines Market Regime using high-fidelity 3-Factor Voting.
        
        Factors:
        1. Trend: Nifty 50 vs 200DMA
        2. Volatility: VIX Percentile
        3. Breadth: Stocks > SMA50
        
        Returns: Dict with regime details.
        """

        votes = {'BULL': 0, 'BEAR': 0, 'SIDEWAYS': 0}
        details = {}
        
        try:
            # --- FACTOR 1: TREND (Nifty 50 vs 200DMA + Momentum Acceleration v9.1) ---
            data = yf.download(index_ticker, period="1y", progress=False)
            if not data.empty:
                if isinstance(data.columns, pd.MultiIndex):
                    prices = data[('Close', index_ticker)]
                else:
                    prices = data['Close']
                
                current_price = float(prices.iloc[-1])
                dma200 = float(prices.rolling(window=200).mean().iloc[-1])
                
                # 1.1 Price vs DMA Offset
                offset = (current_price - dma200) / dma200
                details['trend_offset'] = offset
                
                # 1.2 Momentum Acceleration (ROC of EMA Slope)
                ema200_series = prices.ewm(span=200).mean()
                slope = ema200_series.diff()
                accel = slope.diff() # Change in slope
                
                # Normalize acceleration relative to price for sensitivity
                accel_norm = (accel.iloc[-1] / current_price) * 10000 
                details['momentum_accel'] = accel_norm
                
                # 1.3 Decision Logic with Recovery Shield
                if offset > 0.02:
                    votes['BULL'] += 1
                    details['trend_vote'] = 'BULL'
                elif offset < -0.02:
                    # Recovery Shield: If price is recovering fast (accel > 0.5) 
                    # even if below 200DMA, we soften the BEAR vote.
                    if accel_norm > 0.5:
                        votes['SIDEWAYS'] += 1
                        details['trend_vote'] = 'RECOVERY_SIDEWAYS'
                        print(f"--- Recovery Shield: Accel {accel_norm:.2f} > 0.5. Softening BEAR offset {offset:.1%}")
                    else:
                        votes['BEAR'] += 1
                        details['trend_vote'] = 'BEAR'
                else:
                    votes['SIDEWAYS'] += 1
                    details['trend_vote'] = 'SIDEWAYS'
            
            # --- FACTOR 2: VOLATILITY (VIX Percentile) ---
            vix_threshold, current_vix = self.get_vix_threshold(lookback_days=90)
            # Standard logic: Low VIX = Bull/Sideways, High VIX = Bear/Panic
            # User specified: pct < 30 (Bull), > 70 (Bear)
            # Let's map roughly: < 13 Bull, > 18 Bear
            
            details['vix'] = current_vix
            details['vix_threshold'] = float(vix_threshold)
            if current_vix < 13.5: # Approx 30th percentile
                votes['BULL'] += 1
                details['vix_vote'] = 'BULL'
            elif current_vix > 18.0: # Approx 70th percentile
                votes['BEAR'] += 1
                details['vix_vote'] = 'BEAR'
            else:
                votes['SIDEWAYS'] += 1
                details['vix_vote'] = 'SIDEWAYS'

            # --- FACTOR 3: BREADTH (Nifty > SMA50) ---
            # User: > 1.5 ratio (60/40) -> Bull, < 0.67 (40/60) -> Bear
            breadth_ratio, _ = self.get_market_breadth()
            details['breadth_ratio'] = breadth_ratio
            
            if breadth_ratio > 0.60:
                votes['BULL'] += 1
                details['breadth_vote'] = 'BULL'
            elif breadth_ratio < 0.40:
                votes['BEAR'] += 1
                details['breadth_vote'] = 'BEAR'
            else:
                votes['SIDEWAYS'] += 1
                details['breadth_vote'] = 'SIDEWAYS'
            
            # --- FACTOR 4: HMM REGIME (Hidden Markov Model) ---
            try:
                hmm = RegimeHMM()
                # Use Nifty 50 for HMM
                hmm_regime = hmm.predict_regime(ticker="^NSEI")
                details['hmm_regime'] = hmm_regime
                
                if hmm_regime == "BULLISH":
                    votes['BULL'] += 1
                    details['hmm_vote'] = 'BULL'
                elif hmm_regime == "BEARISH":
                    votes['BEAR'] += 1
                    details['hmm_vote'] = 'BEAR'
                elif hmm_regime == "VOLATILE":
                    votes['SIDEWAYS'] += 1 # Volatile in HMM often maps to sideways/high-risk
                    details['hmm_vote'] = 'SIDEWAYS'
            except Exception as hmm_err:
                logger.warning("Market data: HMM factor error: %s", hmm_err)
            
            # --- CONSENSUS ---
            # Winner takes all
            winner = max(votes, key=votes.get)
            
            # --- PHASE 63: HARDENED OVERRIDES ---
            # 1. VIX Auto-Override (Panic Shield)
            # If VIX > 25, we force BEAR regardless of other factors to preserve capital.
            if current_vix > 25:
                print(f"!!! Panic Shield: VIX {current_vix:.2f} > 25. Forcing BEAR regime. !!!")
                winner = 'BEAR'
            
            # Strategy Mapping
            strategy_map = {
                'BULL': 'MOMENTUM',
                'BEAR': 'QUALITY',
                'SIDEWAYS': 'VALUE'
            }
            
            print(f"--- Regime Votes: {votes} -> Winner: {winner} ---")

            
            return {
                "regime": winner,
                "strategy_suggestion": strategy_map.get(winner, "BALANCED"),
                "details": details,
                "votes": votes
            }
            
        except Exception as e:
            logger.warning("Market data: regime detection failed: %s", e)
            return {"regime": "SIDEWAYS", "strategy_suggestion": "BALANCED", "details": {}, "votes": {"BULL": 0, "BEAR": 0, "SIDEWAYS": 0}}

    def get_batch_history(self, tickers, period="6mo"):
        """
        Fetches historical closing prices for a list of tickers.
        Efficiently downloads in batch.
        
        Args:
            tickers (list): List of symbols (e.g., ['RELIANCE.NS', 'TCS.NS']).
            period (str): '1mo', '3mo', '6mo', '1y'.
            
        Returns:
            pd.DataFrame: Columns are Tickers, Index is Date. Values are Close Prices.
        """
        if not tickers:
            return pd.DataFrame()
            
        try:
            # yfinance expects space-separated string for batch
            tickers_str = " ".join(tickers)
            print(f"--- Fetching history for {len(tickers)} stocks ---")
            
            data = yf.download(tickers_str, period=period, progress=False)
            
            if data.empty:
                return pd.DataFrame()
                
            # Extract Adjusted Close or Close
            if 'Adj Close' in data:
                closes = data['Adj Close']
            elif 'Close' in data:
                closes = data['Close']
            else:
                # Fallback if structure is flat (single ticker)
                closes = data
                
            return closes
            
        except Exception as e:
            logger.warning("Market data: batch history fetch failed: %s", e)
            return pd.DataFrame()


