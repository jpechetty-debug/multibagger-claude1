"""
Feature Factory
================
Central feature computation module for the ML scoring pipeline.

Computes 30+ alpha-generating features from:
- PIT (point-in-time) quarterly data
- multibaggers/microcaps table
- price history in pit_store.db

All functions are stateless — no fitted transforms, no training data leakage.
Missing data is represented as NaN (not zero-filled, since 0 is valid for
growth metrics). The downstream model handles NaN via XGBoost's native support.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from core.observability.logger import get_logger

_log = get_logger("modules.feature_factory")


# ---------------------------------------------------------------------------
# Full feature list — order matters for SHAP / model alignment
# ---------------------------------------------------------------------------

EXTENDED_FEATURES: list[str] = [
    # Original 13
    "score",
    "sales_cagr_5y",
    "avg_roe_5y",
    "pe_ratio",
    "debt_equity",
    "cfo_pat_ratio",
    "market_cap_cr",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "vol_breakout",
    "dist_from_52w_high",
    "roce",
    # Earnings Quality (5)
    "eps_acceleration",
    "revenue_acceleration",
    "opm_expansion_3q",
    "cash_conversion_cycle_change",
    "capex_to_depreciation",
    # Ownership (4)
    "promoter_buying_3m",
    "dii_change_3m",
    "fii_change_3m",
    "pledge_change",
    # Relative Strength (3)
    "rs_vs_nifty_3m",
    "sector_rs_rank",
    "price_vs_200dma",
    # Valuation Context (3)
    "pe_vs_sector_median",
    "peg_ratio",
    "fcf_yield",
    # Size & Liquidity (2)
    "log_market_cap",
    "avg_daily_turnover_cr",
]

EXTENDED_FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    # Original 13
    "score":                      (0.0,    100.0),
    "sales_cagr_5y":              (-100.0, 300.0),
    "avg_roe_5y":                 (-100.0, 200.0),
    "pe_ratio":                   (0.0,    300.0),
    "debt_equity":                (0.0,    10.0),
    "cfo_pat_ratio":              (-5.0,   10.0),
    "market_cap_cr":              (0.0,    5_000_000.0),
    "ret_1m":                     (-1.0,   5.0),
    "ret_3m":                     (-1.0,   10.0),
    "ret_6m":                     (-1.0,   5.0),
    "vol_breakout":               (0.0,    100.0),
    "dist_from_52w_high":         (0.0,    1.0),
    "roce":                       (-100.0, 200.0),
    # Earnings Quality
    "eps_acceleration":           (-5.0,   5.0),
    "revenue_acceleration":       (-5.0,   5.0),
    "opm_expansion_3q":           (-30.0,  30.0),
    "cash_conversion_cycle_change": (-200.0, 200.0),
    "capex_to_depreciation":      (0.0,    10.0),
    # Ownership
    "promoter_buying_3m":         (-20.0,  20.0),
    "dii_change_3m":              (-20.0,  20.0),
    "fii_change_3m":              (-20.0,  20.0),
    "pledge_change":              (-50.0,  50.0),
    # Relative Strength
    "rs_vs_nifty_3m":             (-2.0,   5.0),
    "sector_rs_rank":             (0.0,    1.0),
    "price_vs_200dma":            (-1.0,   5.0),
    # Valuation Context
    "pe_vs_sector_median":        (-5.0,   5.0),
    "peg_ratio":                  (-5.0,   10.0),
    "fcf_yield":                  (-0.5,   0.5),
    # Size & Liquidity
    "log_market_cap":             (0.0,    15.0),
    "avg_daily_turnover_cr":      (0.0,    5000.0),
}


def _sf(val: Any, default: float = 0.0) -> float:
    """Safe float conversion."""
    if val is None:
        return default
    try:
        result = float(val)
        return default if not math.isfinite(result) else result
    except (ValueError, TypeError):
        return default


def _safe_div(num: float, den: float, default: float = 0.0) -> float:
    if den == 0 or not math.isfinite(den):
        return default
    result = num / den
    return result if math.isfinite(result) else default


# ---------------------------------------------------------------------------
# PIT helper — fetch quarterly series for a symbol/metric
# ---------------------------------------------------------------------------

def _pit_series(symbol: str, metric: str, limit: int = 8) -> list[float]:
    """Fetch recent PIT values (newest first) for a symbol/metric pair."""
    try:
        from modules.data_layer.db_utils import get_db_connection

        clean = symbol.replace(".NS", "").replace(".BO", "")
        with get_db_connection("pit_store.db") as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT value FROM pit_data
                WHERE symbol = ? AND metric_name = ?
                ORDER BY as_of_date DESC LIMIT ?
                """,
                (clean, metric, limit),
            )
            return [float(r[0]) for r in cur.fetchall() if r[0] is not None]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Individual feature computations
# ---------------------------------------------------------------------------

def _compute_acceleration(values: list[float]) -> float:
    """Compute rate-of-change of growth from a descending time series.

    Given [q0, q-1, q-2, q-3], computes:
        growth_recent = (q0 - q-1) / |q-1|
        growth_prior  = (q-2 - q-3) / |q-3|
        acceleration  = growth_recent - growth_prior
    """
    if len(values) < 4:
        return np.nan
    q0, q1, q2, q3 = values[0], values[1], values[2], values[3]
    if q1 == 0 or q3 == 0:
        return np.nan
    g_recent = (q0 - q1) / abs(q1)
    g_prior = (q2 - q3) / abs(q3)
    return g_recent - g_prior


def _compute_expansion(values: list[float], periods: int = 3) -> float:
    """Compute absolute change over `periods` from newest-first series."""
    if len(values) < periods:
        return np.nan
    return values[0] - values[periods - 1]


def compute_earnings_quality(symbol: str, data: dict) -> dict[str, float]:
    """Compute 5 earnings-quality features from PIT data."""
    eps_vals = _pit_series(symbol, "eps_quarterly", 4)
    rev_vals = _pit_series(symbol, "revenue_quarterly", 4)
    opm_vals = _pit_series(symbol, "opm", 3)
    ccc_vals = _pit_series(symbol, "cash_conversion_cycle", 2)
    capex_vals = _pit_series(symbol, "capex", 1)
    depr_vals = _pit_series(symbol, "depreciation", 1)

    capex_to_depr = np.nan
    if capex_vals and depr_vals and depr_vals[0] != 0:
        capex_to_depr = abs(capex_vals[0]) / abs(depr_vals[0])

    ccc_change = np.nan
    if len(ccc_vals) >= 2:
        ccc_change = ccc_vals[0] - ccc_vals[1]

    return {
        "eps_acceleration": _compute_acceleration(eps_vals),
        "revenue_acceleration": _compute_acceleration(rev_vals),
        "opm_expansion_3q": _compute_expansion(opm_vals, 3),
        "cash_conversion_cycle_change": ccc_change,
        "capex_to_depreciation": capex_to_depr,
    }


def compute_ownership_signals(symbol: str, data: dict) -> dict[str, float]:
    """Compute 4 ownership-change features."""
    result: dict[str, float] = {}

    # Try PIT data first, fall back to multibaggers table columns
    for feat, pit_metric, _table_key in [
        ("promoter_buying_3m", "promoter_holding", "promoter_holding"),
        ("dii_change_3m", "dii_holding", "dii_holding"),
        ("fii_change_3m", "fii_holding", "fii_holding"),
        ("pledge_change", "promoter_pledge", "pledge_pct"),
    ]:
        series = _pit_series(symbol, pit_metric, 2)
        if len(series) >= 2:
            result[feat] = series[0] - series[1]
        else:
            result[feat] = np.nan

    return result


def compute_relative_strength(symbol: str, data: dict) -> dict[str, float]:
    """Compute 3 relative-strength features from available data."""
    ret_3m = _sf(data.get("ret_3m"), np.nan)

    # rs_vs_nifty: stock 3M return minus Nifty 3M return
    # We use a simple benchmark estimate — Nifty averages ~3% per quarter
    nifty_3m = _get_nifty_3m_return()
    rs_vs_nifty = (ret_3m - nifty_3m) if math.isfinite(ret_3m) else np.nan

    # price_vs_200dma: distance from 200-day moving average
    price_vs_200dma = np.nan
    try:
        from modules.data_layer.db_utils import get_db_connection

        clean = symbol.replace(".NS", "").replace(".BO", "")
        with get_db_connection("pit_store.db") as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT value FROM pit_data
                WHERE symbol = ? AND metric_name = 'price'
                ORDER BY as_of_date DESC LIMIT 200
                """,
                (clean,),
            )
            prices = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
        if len(prices) >= 200:
            dma_200 = sum(prices) / len(prices)
            if dma_200 > 0:
                price_vs_200dma = (prices[0] / dma_200) - 1.0
        elif len(prices) >= 50:
            # Use available data as approximation
            dma = sum(prices) / len(prices)
            if dma > 0:
                price_vs_200dma = (prices[0] / dma) - 1.0
    except Exception:
        pass

    # sector_rs_rank: compute later in batch mode (requires all stocks)
    sector_rs_rank = _sf(data.get("sector_rs_rank"), np.nan)

    return {
        "rs_vs_nifty_3m": rs_vs_nifty,
        "sector_rs_rank": sector_rs_rank,
        "price_vs_200dma": price_vs_200dma,
    }


def _get_nifty_3m_return() -> float:
    """Get Nifty 50 3-month return from DB or use default estimate."""
    try:
        from modules.data_layer.db_utils import get_db_connection

        with get_db_connection("pit_store.db") as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT value FROM pit_data
                WHERE symbol = 'NIFTY50' AND metric_name = 'price'
                ORDER BY as_of_date DESC LIMIT 63
                """,
            )
            prices = [float(r[0]) for r in cur.fetchall() if r[0] is not None]
        if len(prices) >= 2:
            return (prices[0] / prices[-1]) - 1.0
    except Exception:
        pass
    return 0.03  # ~3% quarterly average fallback


def compute_valuation_context(symbol: str, data: dict) -> dict[str, float]:
    """Compute 3 valuation-context features."""
    pe = _sf(data.get("pe_ratio"), np.nan)
    growth = _sf(data.get("sales_cagr_5y"), np.nan)

    # PEG ratio
    peg = np.nan
    if math.isfinite(pe) and math.isfinite(growth) and growth > 0:
        peg = pe / growth

    # PE vs sector median — needs sector data
    pe_vs_sector = _sf(data.get("pe_vs_sector_median"), np.nan)

    # FCF yield = Free Cash Flow / Market Cap
    fcf_yield = np.nan
    mcap = _sf(data.get("market_cap_cr"), 0)
    cfo = _sf(data.get("cfo_pat_ratio"), np.nan)
    pat = _pit_series(symbol, "pat", 1)
    if mcap > 0 and pat and math.isfinite(cfo):
        fcf_approx = pat[0] * cfo  # CFO ≈ PAT * cfo_pat_ratio
        fcf_yield = _safe_div(fcf_approx, mcap * 10_000_000)  # cr to absolute

    return {
        "pe_vs_sector_median": pe_vs_sector,
        "peg_ratio": peg,
        "fcf_yield": fcf_yield,
    }


def compute_size_liquidity(symbol: str, data: dict) -> dict[str, float]:
    """Compute 2 size/liquidity features."""
    mcap = _sf(data.get("market_cap_cr"), np.nan)
    log_mcap = math.log(mcap) if (math.isfinite(mcap) and mcap > 0) else np.nan
    turnover = _sf(data.get("avg_daily_turnover_cr"), np.nan)

    return {
        "log_market_cap": log_mcap,
        "avg_daily_turnover_cr": turnover,
    }


# ---------------------------------------------------------------------------
# Main entry point: compute all features for one stock
# ---------------------------------------------------------------------------

def compute_all_features(symbol: str, data: dict) -> dict[str, float]:
    """Compute all 30+ features for a single stock.

    Args:
        symbol: NSE symbol (e.g. "RELIANCE")
        data: Dict of existing metrics (from multibaggers table or scoring pipeline)

    Returns:
        Dict with all EXTENDED_FEATURES keys. Missing values are NaN.
    """
    result: dict[str, float] = {}

    # Pass through original 13 features
    for feat in EXTENDED_FEATURES[:13]:
        result[feat] = _sf(data.get(feat), np.nan)

    # Compute new feature groups
    result.update(compute_earnings_quality(symbol, data))
    result.update(compute_ownership_signals(symbol, data))
    result.update(compute_relative_strength(symbol, data))
    result.update(compute_valuation_context(symbol, data))
    result.update(compute_size_liquidity(symbol, data))

    return result


# ---------------------------------------------------------------------------
# Batch: compute features for a DataFrame of stocks
# ---------------------------------------------------------------------------

def compute_features_batch(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all features for a DataFrame of stocks.

    Expects columns: symbol + any available metric columns.
    Returns a DataFrame with all EXTENDED_FEATURES columns.
    """
    if df.empty:
        return pd.DataFrame(columns=EXTENDED_FEATURES)

    rows: list[dict[str, float]] = []
    symbols = df["symbol"].tolist() if "symbol" in df.columns else []

    # Compute sector RS ranks in batch
    sector_ranks = _compute_sector_rs_ranks(df)

    # Compute PE vs sector medians in batch
    pe_sector = _compute_pe_vs_sector(df)

    for idx, row in df.iterrows():
        sym = row.get("symbol", f"UNK_{idx}")
        data = row.to_dict()

        # Inject batch-computed values
        data["sector_rs_rank"] = sector_ranks.get(sym, np.nan)
        data["pe_vs_sector_median"] = pe_sector.get(sym, np.nan)

        features = compute_all_features(sym, data)
        rows.append(features)

    result = pd.DataFrame(rows, columns=EXTENDED_FEATURES)
    result.index = df.index
    return result


def _compute_sector_rs_ranks(df: pd.DataFrame) -> dict[str, float]:
    """Compute percentile rank of 3M return within each sector."""
    ranks: dict[str, float] = {}
    if "sector" not in df.columns or "ret_3m" not in df.columns:
        return ranks

    for _sector, group in df.groupby("sector"):
        if len(group) < 2:
            for sym in group["symbol"]:
                ranks[sym] = 0.5
            continue
        pct = group["ret_3m"].rank(pct=True, na_option="bottom")
        for sym, rank_val in zip(group["symbol"], pct, strict=False):
            ranks[sym] = float(rank_val)

    return ranks


def _compute_pe_vs_sector(df: pd.DataFrame) -> dict[str, float]:
    """Compute PE ratio relative to sector median."""
    result: dict[str, float] = {}
    if "sector" not in df.columns or "pe_ratio" not in df.columns:
        return result

    for _sector, group in df.groupby("sector"):
        pe_vals = pd.to_numeric(group["pe_ratio"], errors="coerce")
        median_pe = pe_vals.median()
        if median_pe is None or median_pe == 0 or not math.isfinite(median_pe):
            for sym in group["symbol"]:
                result[sym] = np.nan
            continue
        for sym, pe in zip(group["symbol"], pe_vals, strict=False):
            if math.isfinite(pe) and math.isfinite(median_pe):
                result[sym] = (pe / median_pe) - 1.0
            else:
                result[sym] = np.nan

    return result


# ---------------------------------------------------------------------------
# Sanitizer (replaces the one in hybrid_scoring.py)
# ---------------------------------------------------------------------------

def sanitize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce features to finite floats and clip to EXTENDED_FEATURE_BOUNDS.

    Intentionally stateless — no scaler, no mean-fill from training data.
    Missing columns are NaN-filled; infinite values are NaN-filled.
    XGBoost handles NaN natively.
    """
    out = df.copy()
    for col in EXTENDED_FEATURES:
        if col not in out.columns:
            out[col] = np.nan
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].replace([np.inf, -np.inf], np.nan)
        lo, hi = EXTENDED_FEATURE_BOUNDS.get(col, (-1e9, 1e9))
        out[col] = out[col].clip(lower=lo, upper=hi)
    return out[EXTENDED_FEATURES]
