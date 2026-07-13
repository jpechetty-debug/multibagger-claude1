import asyncio

import numpy as np
import pandas as pd

from modules.retry_utils import run_with_exponential_backoff
from core.observability.logger import get_logger
_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Price history — DB-backed with yfinance lazy fallback
# ---------------------------------------------------------------------------

def _get_price_history_from_db(symbol: str, days: int = 252) -> pd.DataFrame:
    """Fetch cached OHLCV data from data_cache.db or multibaggers table.

    Falls back to yfinance ONLY if DB has no data — but logs a warning
    so we know which symbols still need the Shoonya pipeline.
    """
    try:
        from modules.data_layer.db_utils import get_db_connection

        clean_sym = symbol.replace(".NS", "").replace(".BO", "")
        # Try pit_store for historical price data
        with get_db_connection("pit_store.db") as conn:
            df = pd.read_sql(
                """
                SELECT value AS Close, as_of_date AS Date
                FROM pit_data
                WHERE symbol = ? AND metric_name = 'price'
                ORDER BY as_of_date DESC
                LIMIT ?
                """,
                conn,
                params=(clean_sym, days),
            )
        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.set_index("Date").sort_index()
            return df
    except Exception as exc:
        _log.debug("DB price lookup failed for %s: %s", symbol, exc)

    return pd.DataFrame()


def _get_price_history_fallback(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Last-resort yfinance fallback — logs a deprecation warning."""
    try:
        import yfinance as yf

        _log.warning(
            "DEPRECATION: Using yfinance fallback for %s — migrate to Shoonya/NSE",
            symbol,
        )
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period)
        return df
    except Exception as exc:
        _log.error("yfinance fallback also failed for %s: %s", symbol, exc)
        return pd.DataFrame()


def get_price_history(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """Unified price history: DB first, yfinance fallback.

    Returns a DataFrame with at least a 'Close' column indexed by date.
    """
    days_map = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "2y": 730, "5y": 1825}
    days = days_map.get(period, 180)

    df = _get_price_history_from_db(symbol, days=days)
    if not df.empty and len(df) >= 20:
        return df

    return _get_price_history_fallback(symbol, period=period)


# ---------------------------------------------------------------------------
# Technical indicator calculations (pure math — no data source dependency)
# ---------------------------------------------------------------------------

def calculate_rsi(data, window=14):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_macd(data, slow=26, fast=12, signal=9):
    exp1 = data.ewm(span=fast, adjust=False).mean()
    exp2 = data.ewm(span=slow, adjust=False).mean()
    macd = exp1 - exp2
    signal_line = macd.ewm(span=signal, adjust=False).mean()
    hist = macd - signal_line
    return macd, signal_line, hist


def calculate_bollinger_bands(data, window=20, num_std=2):
    rolling_mean = data.rolling(window=window).mean()
    rolling_std = data.rolling(window=window).std()
    upper_band = rolling_mean + (rolling_std * num_std)
    lower_band = rolling_mean - (rolling_std * num_std)
    return upper_band, rolling_mean, lower_band


def calculate_atr(high, low, close, window=14):
    tr1 = pd.DataFrame(high - low)
    tr2 = pd.DataFrame(abs(high - close.shift(1)))
    tr3 = pd.DataFrame(abs(low - close.shift(1)))
    frames = [tr1, tr2, tr3]
    tr = pd.concat(frames, axis=1, join="inner").max(axis=1)
    atr = tr.rolling(window).mean()
    return atr


# ---------------------------------------------------------------------------
# Technical analysis — uses unified get_price_history()
# ---------------------------------------------------------------------------

async def get_technical_analysis(symbol):
    try:
        df = get_price_history(symbol, period="6mo")

        if df.empty or len(df) < 30:
            return {"error": "Insufficient historical data"}

        close = df["Close"]

        # RSI
        rsi_series = calculate_rsi(close)
        current_rsi = float(rsi_series.iloc[-1])

        # Moving averages
        float(close.rolling(window=20).mean().iloc[-1])
        sma_50 = float(close.rolling(window=50).mean().iloc[-1])
        sma_200 = float(close.rolling(window=200).mean().iloc[-1]) if len(df) >= 200 else sma_50
        current_price = float(close.iloc[-1])

        trend = "Neutral"
        if current_price > sma_50 > sma_200:
            trend = "Strong Bullish"
        elif current_price > sma_50:
            trend = "Bullish"
        elif current_price < sma_50 < sma_200:
            trend = "Strong Bearish"
        elif current_price < sma_50:
            trend = "Bearish"

        strength_score = 50
        if current_price > sma_50:
            strength_score += 15
        if current_price > sma_200:
            strength_score += 15
        if 40 < current_rsi < 70:
            strength_score += 20
        elif current_rsi > 70:
            strength_score += 10
        elif current_rsi < 30:
            strength_score -= 10

        def sanitize_val(value):
            try:
                parsed = float(value)
                if not np.isfinite(parsed):
                    return 0.0
                return parsed
            except Exception as e:
                _log.error(f"Caught unhandled exception: {e}", exc_info=True)
                return 0.0

        return {
            "symbol": symbol,
            "current_price": round(sanitize_val(current_price), 2),
            "rsi": round(sanitize_val(current_rsi), 2),
            "sma_50": round(sanitize_val(sma_50), 2),
            "sma_200": round(sanitize_val(sma_200), 2),
            "trend": trend,
            "strength_score": min(100, int(sanitize_val(strength_score))),
        }
    except Exception as exc:
        return {"error": str(exc)}


def get_sma_200(close):
    try:
        return float(close.rolling(window=200).mean().iloc[-1])
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return None


def calculate_momentum_features(df):
    """
    Calculates momentum and volume breakout features for ML ranking.
    """
    try:
        close = df["Close"]
        volume = df.get("Volume")

        # 1. Price Momentum
        ret_1m = (close.iloc[-1] / close.iloc[-21] - 1) if len(close) > 21 else 0
        ret_3m = (close.iloc[-1] / close.iloc[-63] - 1) if len(close) > 63 else 0
        ret_6m = (close.iloc[-1] / close.iloc[-126] - 1) if len(close) > 126 else 0

        # 2. Volume Breakout (only if volume data exists)
        vol_ratio = 1.0
        if volume is not None and not volume.empty:
            avg_vol_20d = volume.rolling(window=20).mean().iloc[-1]
            current_vol = volume.iloc[-1]
            vol_ratio = (current_vol / avg_vol_20d) if avg_vol_20d > 0 else 1.0

        # 3. 52-Week High Proximity
        high_52w = close.rolling(window=252).max().iloc[-1] if len(close) >= 252 else close.max()
        dist_from_high = (high_52w - close.iloc[-1]) / high_52w if high_52w > 0 else 0

        return {
            "ret_1m": round(ret_1m, 4),
            "ret_3m": round(ret_3m, 4),
            "ret_6m": round(ret_6m, 4),
            "vol_breakout": round(vol_ratio, 2),
            "dist_from_52w_high": round(dist_from_high, 4),
        }
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return {}
