# modules/financial_adapter.py
"""
Sovereign AI — Financial Data Adapter

Decouples raw Yahoo Finance DataFrame extraction from business logic.
The adapter normalizes messy, inconsistently-named DataFrames into a
clean typed dataclass so the CAGR engine and fundamentals module can
be pure math functions that are trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class NormalizedFinancials:
    """Clean, typed representation of a company's financial history.

    All series are oldest-first dicts keyed by year string:
        {"2020": 50000, "2021": 60000, "2022": 72000, "2023": 85000}
    """

    revenue_series: dict[str, float] = field(default_factory=dict)
    net_income_series: dict[str, float] = field(default_factory=dict)
    shares_outstanding_series: dict[str, float] = field(default_factory=dict)
    total_assets_series: dict[str, float] = field(default_factory=dict)
    equity_series: dict[str, float] = field(default_factory=dict)
    data_points: int = 0


# ── Fuzzy Key Extraction ──────────────────────────────────────────────────────

_REVENUE_KEYS = [
    "Total Revenue",
    "Operating Revenue",
    "Revenue From Operations",
    "Net Sales",
]

_NET_INCOME_KEYS = [
    "Net Income",
    "Net Profit",
    "PAT",
    "Profit After Tax",
]

_SHARES_KEYS = [
    "Ordinary Shares Number",
    "Share Issued",
    "Common Stock",
]

_TOTAL_ASSETS_KEYS = [
    "Total Assets",
]

_EQUITY_KEYS = [
    "Stockholders Equity",
    "Common Stock Equity",
    "Total Equity",
    "Shareholders Equity",
]


def _extract_series(df: pd.DataFrame, keys: list[str]) -> pd.Series | None:
    """Extract a time-series row using exact then fuzzy matching."""
    if df is None or df.empty:
        return None

    # Exact match first
    for key in keys:
        if key in df.index:
            return df.loc[key]

    # Fuzzy fallback
    for key in keys:
        for idx_name in df.index:
            if key.lower() in idx_name.lower():
                return df.loc[idx_name]

    return None


def _series_to_dict(series: pd.Series | None) -> dict[str, float]:
    """Convert a pandas Series to a year-keyed dict, oldest first."""
    if series is None:
        return {}

    result = {}
    for col in series.index:
        year_key = col.strftime("%Y") if hasattr(col, "strftime") else str(col)
        val = series[col]
        if pd.notna(val):
            result[year_key] = float(val)

    # Reverse to oldest-first if the first key is newer than the last
    keys = list(result.keys())
    if len(keys) >= 2 and keys[0] > keys[-1]:
        result = dict(reversed(list(result.items())))

    return result


def extract_normalized_financials(ticker) -> NormalizedFinancials:
    """Extract and normalize financial data from a yfinance Ticker.

    This is the single place where fuzzy key matching happens.
    Downstream code receives clean, typed data.
    """
    try:
        fin = ticker.financials
        if fin is None or (isinstance(fin, pd.DataFrame) and fin.empty):
            return NormalizedFinancials()
    except Exception:
        return NormalizedFinancials()

    try:
        bs = ticker.balance_sheet
        if bs is None or (isinstance(bs, pd.DataFrame) and bs.empty):
            bs = pd.DataFrame()
    except Exception:
        bs = pd.DataFrame()

    revenue = _series_to_dict(_extract_series(fin, _REVENUE_KEYS))
    net_income = _series_to_dict(_extract_series(fin, _NET_INCOME_KEYS))
    shares = _series_to_dict(_extract_series(bs, _SHARES_KEYS))
    total_assets = _series_to_dict(_extract_series(bs, _TOTAL_ASSETS_KEYS))
    equity = _series_to_dict(_extract_series(bs, _EQUITY_KEYS))

    data_points = max(len(revenue), len(net_income), 0)

    return NormalizedFinancials(
        revenue_series=revenue,
        net_income_series=net_income,
        shares_outstanding_series=shares,
        total_assets_series=total_assets,
        equity_series=equity,
        data_points=data_points,
    )
