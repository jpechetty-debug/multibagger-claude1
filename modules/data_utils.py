# modules/data_utils.py
import asyncio
import os
import threading

import pandas as pd
import pandas_market_calendars as mcal


def run_coroutine_sync(coro):
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
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()

    if "value" in error:
        raise error["value"]

    return result.get("value")


def get_valid_trading_days(start_date, end_date):
    nse = mcal.get_calendar("NSE")
    schedule = nse.schedule(start_date=start_date, end_date=end_date)
    return schedule.index.date


def load_tickers_from_csv(file_paths):
    """
    Reads multiple CSV files, extracts symbols, deduplicates, and formats them for yfinance (.NS).
    """
    all_symbols = set()
    for file_path in file_paths:
        if not os.path.exists(file_path):
            continue
        try:
            df = pd.read_csv(file_path)
            df.columns = df.columns.str.strip()
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
        except Exception:
            continue
    return list(all_symbols)
