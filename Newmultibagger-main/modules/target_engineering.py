"""
Target Engineering
===================
Compute forward returns and binary multibagger classification targets
for the ML training pipeline.

Replaces the yfinance-based forward price fetcher with DB-only lookups.
Prices come from the full-universe price_history table (pit_store.db).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from core.observability.logger import get_logger

_log = get_logger("modules.target_engineering")

# Multibagger thresholds per forward horizon (months). 3M ~ the 6M pace compounded.
MULTIBAGGER_THRESHOLDS = {3: 0.15, 6: 0.30, 12: 0.50}
MULTIBAGGER_6M_THRESHOLD = MULTIBAGGER_THRESHOLDS[6]
MULTIBAGGER_12M_THRESHOLD = MULTIBAGGER_THRESHOLDS[12]

ENTRY_TOLERANCE_DAYS = 7   # last close on/before the snapshot date
EXIT_TOLERANCE_DAYS = 10   # first close on/after the target date


def _clean_symbol(sym) -> str:
    return str(sym).replace(".NS", "").replace(".BO", "")


def _asof_prices(df: pd.DataFrame, when: pd.Series, direction: str, tolerance_days: int) -> pd.Series:
    """Close from price_history nearest ``when`` per row (backward = on/before, forward = on/after)."""
    out = pd.Series(np.nan, index=df.index, dtype=float)
    try:
        from modules.data_layer.price_history import load_closes
        prices = load_closes()
    except Exception as exc:
        _log.error("Failed to load price_history", error=str(exc))
        return out
    if prices.empty or df.empty:
        return out

    prices["key"] = prices["symbol"].map(_clean_symbol)
    left = pd.DataFrame({"key": df["symbol"].map(_clean_symbol), "when": pd.to_datetime(when, errors="coerce"), "row": df.index})
    left = left.dropna(subset=["when"]).sort_values("when")
    merged = pd.merge_asof(
        left,
        prices[["key", "date", "close"]].sort_values("date"),
        left_on="when", right_on="date", by="key",
        direction=direction, tolerance=pd.Timedelta(days=tolerance_days),
    )
    out.loc[merged["row"].to_numpy()] = merged["close"].to_numpy()
    return out


def fetch_forward_prices_db(
    df: pd.DataFrame,
    months: int = 6,
) -> pd.Series:
    """Adjusted close ``months`` after each (symbol, as_of_date) row, from price_history.

    NaN where the horizon has not elapsed yet or the symbol has no prices.
    """
    if df.empty:
        return pd.Series(dtype=float)
    target = pd.to_datetime(df["as_of_date"], errors="coerce") + pd.DateOffset(months=months)
    return _asof_prices(df, target, "forward", EXIT_TOLERANCE_DAYS)


def fetch_entry_prices_db(df: pd.DataFrame) -> pd.Series:
    """Adjusted close on/before each row's as_of_date, from price_history."""
    if df.empty:
        return pd.Series(dtype=float)
    return _asof_prices(df, df["as_of_date"], "backward", ENTRY_TOLERANCE_DAYS)


def build_training_targets(
    df: pd.DataFrame,
    horizon_months: int = 3,
) -> pd.DataFrame:
    """Attach forward returns and binary multibagger label to PIT rows.

    Entry and exit prices both come from the adjusted price_history, so splits and
    bonuses do not show up as returns. The snapshot's own price is not used.

    Returns rows with:
        - entry_price, forward_price
        - forward_return: (forward_price - entry_price) / entry_price
        - is_multibagger: 1 if forward_return > the horizon's threshold
    """
    out = df.copy()
    out["entry_price"] = fetch_entry_prices_db(out)
    out["forward_price"] = fetch_forward_prices_db(out, months=horizon_months)
    out = out.dropna(subset=["entry_price", "forward_price"])
    out = out[out["entry_price"] > 0]

    if out.empty:
        _log.info("No valid forward-return pairs found", horizon=f"{horizon_months}M")
        return out

    out["forward_return"] = (out["forward_price"] - out["entry_price"]) / out["entry_price"]
    out = out.replace([np.inf, -np.inf], np.nan).dropna(subset=["forward_return"])

    threshold = MULTIBAGGER_THRESHOLDS.get(horizon_months, MULTIBAGGER_THRESHOLDS[12])
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
