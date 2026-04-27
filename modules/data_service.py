# modules/data_service.py
"""
Sovereign Terminal — Data Service Orchestrator
Modularized into: adapters/, normalization/, data_utils.py
"""
import asyncio
import time
import pickle
import sqlite3
import logging
import yfinance as yf
import pandas as pd
from typing import Dict, List, Optional, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# -- Modular Imports --
from modules.adapters.yfinance import YFinanceProvider
from modules.adapters.nse import PNSEAProvider, NSEPythonProvider
from modules.normalization.cleaner import is_payload_skeletal, json_safe_clean
from modules.data_utils import run_coroutine_sync, get_valid_trading_days, load_tickers_from_csv

logger = logging.getLogger(__name__)

_TRANSIENT_ERROR_HINTS = (
    "timeout", "timed out", "429", "rate limit", "too many requests",
    "temporarily unavailable", "connection reset", "ssl", "name resolution",
    "401", "unauthorized",
)

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
                if row: return pickle.loads(row[0])
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

class DataManager:
    def __init__(self, max_concurrency: int = 15):
        self.max_concurrency = int(max_concurrency)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self.provider_timeout_seconds = 3
        self.yfinance_timeout_seconds = 8
        self.history_timeout_seconds = 6
        self.provider_fail_streak = {}
        self.provider_cooldown_until = {}
        
        self.providers = [
            PNSEAProvider(self.executor),
            NSEPythonProvider(self.executor),
            YFinanceProvider(self.executor)
        ]
        
        self.cache = PersistentCache()
        current_year = datetime.now().year
        self.valid_trading_days = get_valid_trading_days(f'{current_year-10}-01-01', f'{current_year+2}-12-31')

    async def __aenter__(self): return self
    async def __aexit__(self, exc_type, exc_val, exc_tb): await self.close()

    def _is_transient_error(self, exc: Exception) -> bool:
        if isinstance(exc, (asyncio.TimeoutError, TimeoutError)): return True
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
        if streak <= 1: return
        pause_seconds = min(2.5, 0.2 * streak)
        await asyncio.sleep(pause_seconds)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asyncio.TimeoutError, TimeoutError)),
    )
    async def async_fetch_fundamentals(self, symbol: str) -> Dict:
        async with self.semaphore:
            cache_key = f"fund_{symbol}"
            cached = self.cache.get(cache_key)
            if cached:
                cached['data_freshness'] = 'live (cached within TTL)'
                return cached

            incomplete_payload = None
            for provider in self.providers:
                if not getattr(provider, 'available', True): continue
                provider_name = provider.name
                if self.provider_cooldown_until.get(provider_name, 0) > time.time(): continue
                try:
                    timeout_s = self.yfinance_timeout_seconds if provider_name == "yfinance" else self.provider_timeout_seconds
                    data = await asyncio.wait_for(provider.fetch_fundamentals(symbol), timeout=timeout_s)
                    if data and "error" not in data:
                        if is_payload_skeletal(data):
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
                    if transient: await self._adaptive_pause(provider_name)
                    logger.warning(f"Provider {provider.name} failed for {symbol}: {e}")
                    continue

            if incomplete_payload:
                incomplete_payload['data_freshness'] = 'stale (incomplete fallback)'
                return incomplete_payload
            
            stale_cached = self.cache.get_expired(cache_key)
            if stale_cached:
                stale_cached['data_freshness'] = 'stale (beyond TTL)'
                stale_cached['error'] = 'All providers failed, returning stale cache'
                return stale_cached
            
            return {"symbol": symbol, "error": "All providers failed", "data_freshness": "stale (no cache)", "source": "fallback_failed"}

    def fetch_fundamentals(self, symbol: str) -> Dict:
        return run_coroutine_sync(self.async_fetch_fundamentals(symbol))

    async def async_fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
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
            
            if df.empty or 'Close' not in df.columns: return pd.DataFrame()
            pct_change = df['Close'].pct_change().abs()
            glitch_mask = (df['Close'] > 10) & (pct_change > 0.5)
            if glitch_mask.any(): df = df[~glitch_mask]
            if 'Volume' in df.columns: df.loc[df['Volume'] < 0, 'Volume'] = 0
            
            today = datetime.now().date()
            if today not in self.valid_trading_days:
                if len(df) >= 2 and 'Volume' in df.columns and (pd.isna(df['Volume'].iloc[-1]) or df['Volume'].iloc[-1] == 0):
                    df = df.iloc[:-1]
            return df

    def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        return run_coroutine_sync(self.async_fetch_history(symbol, period=period))

    async def async_fetch_quarterly_results(self, symbol: str) -> List[Dict]:
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
        return run_coroutine_sync(self.async_fetch_quarterly_results(symbol))

    async def fetch_batch(self, symbols: List[str]) -> Dict[str, Dict]:
        tasks = [self.async_fetch_fundamentals(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {sym: res for sym, res in zip(symbols, results) if not isinstance(res, Exception)}

    async def close(self): self.executor.shutdown(wait=True)

data_manager = DataManager()

def analyze_market_regime(symbol="^NSEI"):
    """Legacy helper for market regime analysis."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y")
        if len(hist) < 200: return "Unknown"
        sma_50 = hist['Close'].tail(50).mean()
        sma_200 = hist['Close'].tail(200).mean()
        current_price = hist['Close'].iloc[-1]
        if current_price > sma_50 and sma_50 > sma_200: return "Bull Market"
        elif current_price < sma_50 and sma_50 < sma_200: return "Bear Market"
        elif current_price < sma_50 and current_price > sma_200: return "Correction"
        elif current_price > sma_50 and current_price < sma_200: return "Recovery"
        return "Sideways"
    except Exception: return "Unknown"

class MarketDataProvider:
    """Shim for legacy callers."""
    def get_market_regime(self, symbol="^NSEI"):
        regime = analyze_market_regime(symbol)
        return {"regime": regime, "symbol": symbol, "timestamp": time.time()}
