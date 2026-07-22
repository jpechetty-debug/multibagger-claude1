from datetime import date
import pandas as pd
from jugaad_data.nse import stock_df
from core.observability.logger import get_logger

logger = get_logger("adapters.jugaad")

def get_jugaad_history(symbol: str, from_date: date, to_date: date) -> pd.DataFrame:
    """
    Fetch price history for a non-index NSE symbol using jugaad-data.
    Returns a dataframe mapped to standard Open/High/Low/Close/Volume schema.
    """
    if symbol.endswith(".BO"):
        logger.warning(f"jugaad-data does not support BSE symbols ({symbol})")
        return pd.DataFrame()
        
    nse_symbol = symbol.replace(".NS", "")
    
    try:
        data = stock_df(symbol=nse_symbol, from_date=from_date, to_date=to_date)
    except Exception as e:
        logger.warning(f"jugaad-data failed for {symbol}: {e}")
        return pd.DataFrame()

    if data is None:
        return pd.DataFrame()
    if isinstance(data, pd.DataFrame):
        if data.empty:
            return pd.DataFrame()
    elif not data:
        return pd.DataFrame()

    try:
        df = pd.DataFrame(data)
        if df.empty:
            return df

        # jugaad-data schema map to standard yfinance schema
        if "DATE" in df.columns:
            df["Date"] = pd.to_datetime(df["DATE"])
        else:
            df["Date"] = pd.to_datetime(df.index)

        df = df.set_index("Date")

        # Standardize columns to Title Case like yfinance
        rename_map = {
            "OPEN": "Open", "HIGH": "High", "LOW": "Low", 
            "CLOSE": "Close", "close": "Close", "PREV. CLOSE": "Prev_Close",
            "VOLUME": "Volume", "volume": "Volume"
        }
        df.rename(columns=rename_map, inplace=True)
        df.sort_index(inplace=True)

        # Ensure we return only the standard columns if they exist
        cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
        return df[cols]
    except Exception as e:
        logger.error(f"jugaad-data normalization failed for {symbol}: {e}")
        return pd.DataFrame()
