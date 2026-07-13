"""
Target Engineering
===================
Compute forward returns and binary multibagger classification targets
for the ML training pipeline.

Replaces the yfinance-based forward price fetcher with DB-only lookups.
Uses pit_store.db and survivorship_adjusted_loader for bias-free targets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.observability.logger import get_logger

_log = get_logger("modules.target_engineering")

# Multibagger thresholds
MULTIBAGGER_6M_THRESHOLD = 0.30   # 30% return in 6 months
MULTIBAGGER_12M_THRESHOLD = 0.50  # 50% return in 12 months


def fetch_forward_prices_db(
    df: pd.DataFrame,
    months: int = 6,
) -> pd.Series:
    """Fetch forward prices from pit_store.db for each (symbol, as_of_date) row.

    Returns a Series aligned with df.index containing forward prices.
    NaN where data is unavailable.
    """
    if df.empty:
        return pd.Series(dtype=float)

    try:
        from modules.data_layer.db_utils import get_db_connection
    except ImportError:
        _log.error("Cannot import db_utils — returning empty series")
        return pd.Series(np.nan, index=df.index)

    out = pd.Series(np.nan, index=df.index, dtype=float)
    df = df.copy()
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    df["target_date"] = df["as_of_date"] + pd.DateOffset(months=months)

    try:
        with get_db_connection("pit_store.db") as conn:
            # Bulk-load all price data once
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
        _log.error("Failed to load price data from pit_store.db", error=str(exc))
        return out

    if price_df.empty:
        return out

    price_df["as_of_date"] = pd.to_datetime(price_df["as_of_date"], errors="coerce")
    price_df["price"] = pd.to_numeric(price_df["price"], errors="coerce")
    price_df = price_df.dropna()

    # Index by symbol for fast lookup
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

        # Find closest price on or after target_date
        future = sym_prices[sym_prices.index >= target_date]
        if future.empty:
            continue

        closest_date = future.index[0]
        if (closest_date - target_date).days <= 45:  # Allow 45-day tolerance
            out.at[idx] = float(future.iloc[0]["price"])

    return out


def build_training_targets(
    df: pd.DataFrame,
    horizon_months: int = 6,
) -> pd.DataFrame:
    """Attach forward returns and binary multibagger label to PIT rows.

    Args:
        df: DataFrame with 'symbol', 'as_of_date', 'pit_price' columns.
        horizon_months: Forward return horizon (default 6 months).

    Returns:
        DataFrame with added columns:
        - forward_price: price at T + horizon_months
        - forward_return: (forward_price - pit_price) / pit_price
        - is_multibagger: 1 if forward_return > threshold, 0 otherwise
    """
    out = df.copy()

    # Fetch forward prices
    out["forward_price"] = fetch_forward_prices_db(out, months=horizon_months)
    out = out.dropna(subset=["pit_price", "forward_price"])
    out = out[out["pit_price"] > 0]

    if out.empty:
        _log.info("No valid forward-return pairs found")
        return out

    out["forward_return"] = (out["forward_price"] - out["pit_price"]) / out["pit_price"]
    out.replace([np.inf, -np.inf], np.nan, inplace=True)
    out = out.dropna(subset=["forward_return"])

    # Binary target
    threshold = (
        MULTIBAGGER_6M_THRESHOLD if horizon_months <= 6
        else MULTIBAGGER_12M_THRESHOLD
    )
    out["is_multibagger"] = (out["forward_return"] > threshold).astype(int)

    _log.info(
        "Training targets built",
        rows=len(out),
        multibaggers=int(out["is_multibagger"].sum()),
        hit_rate=round(out["is_multibagger"].mean() * 100, 1),
        horizon=f"{horizon_months}M",
    )

    return out


def load_pit_with_features() -> pd.DataFrame:
    """Load PIT data with all available features for training.

    Combines fundamentals_pit with feature_factory output.
    """
    try:
        from modules.data_layer.db_utils import get_db_connection
        from modules.feature_factory import compute_features_batch

        with get_db_connection("stocks.db") as conn:
            pit_df = pd.read_sql(
                """
                SELECT symbol, as_of_date,
                       source_updated_at AS report_date,
                       price AS pit_price,
                       score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                       debt_equity, cfo_pat_ratio, market_cap_cr,
                       ret_1m, ret_3m, ret_6m,
                       vol_breakout, dist_from_52w_high, roce,
                       sector
                FROM fundamentals_pit
                """,
                conn,
            )

        if pit_df.empty:
            _log.info("fundamentals_pit table is empty")
            return pit_df

        # Compute extended features
        feature_df = compute_features_batch(pit_df)

        # Merge features back with metadata
        result = pit_df[["symbol", "as_of_date", "pit_price"]].copy()
        result = pd.concat([result.reset_index(drop=True), feature_df.reset_index(drop=True)], axis=1)

        return result

    except Exception as exc:
        _log.error("Failed to load PIT data with features", error=str(exc))
        return pd.DataFrame()
