"""
Market regime analysis, sector rotation, and benchmark returns.

Extracted from scripts/internal/screener.py.
"""

import polars as pl
from db.db_core import duck_conn

def analyze_market_regime(symbol="^NSEI"):
    """Determines Market Regime using DuckDB against the local database."""
    try:
        # Since we migrated away from yfinance, we use local data.
        # Note: If benchmark indices aren't in fundamentals_pit, this would need a dedicated index table.
        # For now, we query the lake using DuckDB.
        query = f"""
            SELECT as_of_date, price as Close
            FROM read_parquet('data/lake/daily/{symbol}.parquet')
            ORDER BY as_of_date DESC
            LIMIT 200
        """
        df = duck_conn.execute(query).df()
        
        if len(df) < 200:
            return "Unknown"

        sma_50 = df["Close"].head(50).mean()
        sma_200 = df["Close"].mean()
        current_price = df["Close"].iloc[0]

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
    """Analyze relative sector performance for rotation signals using DuckDB."""
    results = {}
    
    # Define period mapping to available columns in Parquet
    ret_col = "ret_3m" if period == "3mo" else "ret_1m"
    
    for sector, symbols in sector_stocks.items():
        sector_returns = []
        for sym in symbols[:5]:
            try:
                query = f"""
                    SELECT {ret_col}
                    FROM read_parquet('data/lake/daily/{sym}.parquet')
                    ORDER BY as_of_date DESC
                    LIMIT 1
                """
                ret = duck_conn.execute(query).fetchone()
                if ret and ret[0] is not None:
                    # ret_3m is typically stored as a percentage or fraction. 
                    sector_returns.append(ret[0])

            except Exception:
                continue
        if sector_returns:
            results[sector] = sum(sector_returns) / len(sector_returns)
    return dict(sorted(results.items(), key=lambda x: x[1], reverse=True))


def get_benchmark_return(symbol="^NSEI", period="1y"):
    """Fetch benchmark index return for the given period using DuckDB."""
    try:
        # Assuming ret_1y is not explicitly in parquet, we could calculate it or use existing returns.
        # But for now, we map '1y' to retrieving the oldest vs newest price within 252 trading days.
        query = f"""
            SELECT price as Close
            FROM read_parquet('data/lake/daily/{symbol}.parquet')
            ORDER BY as_of_date DESC
            LIMIT 252
        """
        df = duck_conn.execute(query).df()
        
        if len(df) >= 2:
            return round((df["Close"].iloc[0] / df["Close"].iloc[-1] - 1) * 100, 2)
    except Exception:
        pass
    return 0.0
