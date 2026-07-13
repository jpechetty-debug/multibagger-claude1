"""
Price Utilities — DB-Backed
============================
Fetch forward prices from pit_store.db for PIT training data.
Replaces the yfinance-based implementation.
"""

import numpy as np
import pandas as pd

from core.observability.logger import get_logger

_log = get_logger("modules.price_utils")


def fetch_forward_prices(df_input: pd.DataFrame, months: int = 3) -> pd.Series:
    """Fetch forward prices from pit_store.db.

    This is the backward-compatible wrapper. Internally delegates to
    target_engineering.fetch_forward_prices_db().
    """
    try:
        from modules.target_engineering import fetch_forward_prices_db
        return fetch_forward_prices_db(df_input, months=months)
    except ImportError:
        _log.warning("target_engineering not available, using inline DB lookup")

    return _fetch_forward_prices_inline(df_input, months)


def _fetch_forward_prices_inline(
    df_input: pd.DataFrame,
    months: int = 3,
) -> pd.Series:
    """Inline fallback: fetch forward prices directly from pit_store.db."""
    df = df_input.copy()
    out = pd.Series(np.nan, index=df.index, dtype=float)

    try:
        from modules.data_layer.db_utils import get_db_connection
    except ImportError:
        _log.error("Cannot import db_utils")
        return out

    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    df["target_date"] = df["as_of_date"] + pd.DateOffset(months=months)

    try:
        with get_db_connection("pit_store.db") as conn:
            price_df = pd.read_sql(
                """
                SELECT symbol, as_of_date, value AS price
                FROM pit_data
                WHERE metric_name = 'price' AND value IS NOT NULL
                ORDER BY symbol, as_of_date
                """,
                conn,
            )
    except Exception as exc:
        _log.error("Failed to load price data", error=str(exc))
        return out

    if price_df.empty:
        return out

    price_df["as_of_date"] = pd.to_datetime(price_df["as_of_date"], errors="coerce")
    price_df["price"] = pd.to_numeric(price_df["price"], errors="coerce")
    price_df = price_df.dropna()

    price_by_sym: dict[str, pd.DataFrame] = {}
    for sym, grp in price_df.groupby("symbol"):
        price_by_sym[str(sym)] = grp.set_index("as_of_date").sort_index()

    for idx, row in df.iterrows():
        sym = str(row.get("symbol", ""))
        clean = sym.replace(".NS", "").replace(".BO", "")
        target_date = row.get("target_date")

        if pd.isna(target_date):
            continue

        sym_prices = price_by_sym.get(clean)
        if sym_prices is None or sym_prices.empty:
            continue

        future = sym_prices[sym_prices.index >= target_date]
        if future.empty:
            continue

        closest_date = future.index[0]
        if (closest_date - target_date).days <= 35:
            out.at[idx] = float(future.iloc[0]["price"])

    return out
