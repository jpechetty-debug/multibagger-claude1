"""
Market regime analysis, sector rotation, and benchmark returns.

Extracted from scripts/internal/screener.py.
"""

import yfinance as yf


def analyze_market_regime(symbol="^NSEI"):
    """Determines Market Regime: Bull, Bear, Correction, Sideways."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y")

        if len(hist) < 200:
            return "Unknown"

        sma_50 = hist["Close"].tail(50).mean()
        sma_200 = hist["Close"].tail(200).mean()
        current_price = hist["Close"].iloc[-1]

        if current_price > sma_50 > sma_200:
            return "BULL"
        elif current_price < sma_50 < sma_200:
            return "BEAR"
        elif current_price < sma_200:
            return "CORRECTION"
        else:
            return "SIDEWAYS"
    except Exception:
        return "SIDEWAYS"


def analyze_sector_rotation(sector_stocks, period="3mo"):
    """Analyze relative sector performance for rotation signals."""
    results = {}
    for sector, symbols in sector_stocks.items():
        returns = []
        for sym in symbols[:5]:
            try:
                hist = yf.Ticker(sym).history(period=period)
                if len(hist) >= 2:
                    ret = (hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                    returns.append(ret)
            except Exception:
                continue
        if returns:
            results[sector] = round(sum(returns) / len(returns), 2)
    return dict(sorted(results.items(), key=lambda x: x[1], reverse=True))


def get_benchmark_return(symbol="^NSEI", period="1y"):
    """Fetch benchmark index return for the given period."""
    try:
        hist = yf.Ticker(symbol).history(period=period)
        if len(hist) >= 2:
            return round((hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100, 2)
    except Exception:
        pass
    return 0.0
