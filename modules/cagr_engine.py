"""
Multi-Period CAGR Engine
========================
Computes Compound Annual Growth Rates for Revenue, PAT, and EPS
across 3-year, 5-year, and 10-year horizons.

Used to measure compounding consistency — the single biggest
predictor of multibagger potential.
"""

from __future__ import annotations

from typing import cast

import pandas as pd


def _safe_cagr(start_val: float, end_val: float, years: int) -> float | None:
    """Computes CAGR with safety checks for negative/zero values."""
    if years <= 0 or start_val <= 0 or end_val <= 0:
        return None
    try:
        cagr = (end_val / start_val) ** (1.0 / years) - 1.0
        return cast(float, round(cagr * 100, 2))
    except (ZeroDivisionError, ValueError, OverflowError):
        return None


def _extract_series(df: pd.DataFrame, keys: list[str]) -> pd.Series | None:
    """Extract a time-series row from a financial statement DataFrame."""
    if df.empty:
        return None
    for key in keys:
        if key in df.index:
            return df.loc[key]
    # Fuzzy match fallback
    for key in keys:
        for idx_name in df.index:
            if key.lower() in idx_name.lower():
                return df.loc[idx_name]
    return None


def _compute_multi_period_cagr(
    series: pd.Series,
    periods: dict[str, int],
) -> dict[str, float | None]:
    """
    Given a time-series (oldest-first after reversal), compute CAGRs
    for each named period.
    """
    # Reverse to oldest-first if not already
    if series.index[0] > series.index[-1]:
        series = series.iloc[::-1]

    total_points = len(series)
    end_val = series.iloc[-1]

    if pd.isna(end_val) or end_val <= 0:
        return dict.fromkeys(periods)

    result = {}
    for name, years in periods.items():
        # Each year is roughly 1 data point in annual statements
        idx = total_points - 1 - years
        if idx >= 0:
            start_val = series.iloc[idx]
            if pd.notna(start_val) and start_val > 0:
                result[name] = _safe_cagr(float(start_val), float(end_val), years)
            else:
                result[name] = None
        else:
            result[name] = None
    return result


def _cagr_from_series(
    series: dict[str, float],
    periods: dict[str, int],
) -> dict[str, float | None]:
    """Compute CAGRs from a year-keyed dict (oldest-first)."""
    values = list(series.values())
    total_points = len(values)
    if total_points < 2:
        return dict.fromkeys(periods)

    end_val = values[-1]
    if end_val <= 0:
        return dict.fromkeys(periods)

    result = {}
    for name, years in periods.items():
        idx = total_points - 1 - years
        if idx >= 0:
            start_val = values[idx]
            if start_val is not None and start_val > 0:
                result[name] = _safe_cagr(start_val, end_val, years)
            else:
                result[name] = None
        else:
            result[name] = None
    return result


def calculate_all_cagrs_from_normalized(fin) -> dict[str, float | str | None]:
    """Pure math CAGR calculation from a NormalizedFinancials dataclass.

    This function has zero dependencies on yfinance or pandas,
    making it perfectly unit-testable with static data.

    Args:
        fin: A NormalizedFinancials instance from financial_adapter.

    Returns:
        Same shape as calculate_all_cagrs().
    """
    default: dict[str, float | str | None] = {
        "Revenue_CAGR_3Y": None,
        "Revenue_CAGR_5Y": None,
        "PAT_CAGR_3Y": None,
        "PAT_CAGR_5Y": None,
        "EPS_CAGR_3Y": None,
        "EPS_CAGR_5Y": None,
        "CAGR_Consistency": "UNKNOWN",
    }

    if fin.data_points < 2:
        return default

    available_years = fin.data_points
    periods = {"3Y": 3, "5Y": min(4, available_years - 1)}
    if available_years >= 5:
        periods["5Y"] = 4

    # Revenue CAGR
    rev_cagrs = _cagr_from_series(fin.revenue_series, periods) if fin.revenue_series else {}

    # PAT CAGR
    pat_cagrs = _cagr_from_series(fin.net_income_series, periods) if fin.net_income_series else {}

    # EPS CAGR (Net Income / Shares Outstanding)
    eps_cagrs: dict[str, float | None] = {}
    if fin.net_income_series and fin.shares_outstanding_series:
        common_years = sorted(
            set(fin.net_income_series) & set(fin.shares_outstanding_series)
        )
        if len(common_years) >= 2:
            eps_series = {}
            for year in common_years:
                shares = fin.shares_outstanding_series[year]
                if shares and shares > 0:
                    eps_series[year] = fin.net_income_series[year] / shares
            if len(eps_series) >= 2:
                eps_periods = {k: v for k, v in periods.items() if v < len(eps_series)}
                eps_cagrs = _cagr_from_series(eps_series, eps_periods)

    # Consistency
    all_cagrs = [v for v in list(rev_cagrs.values()) + list(pat_cagrs.values()) if v is not None]
    if len(all_cagrs) >= 2:
        above_15 = sum(1 for c in all_cagrs if c >= 15)
        above_10 = sum(1 for c in all_cagrs if c >= 10)
        if above_15 >= len(all_cagrs) * 0.75:
            consistency = "HIGH"
        elif above_10 >= len(all_cagrs) * 0.5:
            consistency = "MEDIUM"
        else:
            consistency = "LOW"
    else:
        consistency = "UNKNOWN"

    return {
        "Revenue_CAGR_3Y": rev_cagrs.get("3Y"),
        "Revenue_CAGR_5Y": rev_cagrs.get("5Y"),
        "PAT_CAGR_3Y": pat_cagrs.get("3Y"),
        "PAT_CAGR_5Y": pat_cagrs.get("5Y"),
        "EPS_CAGR_3Y": eps_cagrs.get("3Y"),
        "EPS_CAGR_5Y": eps_cagrs.get("5Y"),
        "CAGR_Consistency": consistency,
    }


def calculate_all_cagrs(ticker) -> dict[str, float | str | None]:
    """
    Compute Revenue, PAT, and EPS CAGRs for 3Y, 5Y periods.

    Args:
        ticker: A yfinance Ticker or TickerShim with .financials and .balance_sheet

    Returns:
        {
            "Revenue_CAGR_3Y": 18.5,
            "Revenue_CAGR_5Y": 15.2,
            "PAT_CAGR_3Y": 22.1,
            "PAT_CAGR_5Y": 19.8,
            "EPS_CAGR_3Y": 20.0,
            "EPS_CAGR_5Y": 17.5,
            "CAGR_Consistency": "HIGH"   # HIGH / MEDIUM / LOW
        }
    """
    default: dict[str, float | str | None] = {
        "Revenue_CAGR_3Y": None,
        "Revenue_CAGR_5Y": None,
        "PAT_CAGR_3Y": None,
        "PAT_CAGR_5Y": None,
        "EPS_CAGR_3Y": None,
        "EPS_CAGR_5Y": None,
        "CAGR_Consistency": "UNKNOWN",
    }

    try:
        fin = ticker.financials
        if fin is None or (isinstance(fin, pd.DataFrame) and fin.empty):
            return default
    except Exception:
        return default

    periods = {"3Y": 3, "5Y": min(4, len(fin.columns) - 1)}
    # yfinance annual financials typically have 4 columns (4 years)
    # Adjust 5Y to available data
    available_years = len(fin.columns)
    if available_years >= 5:
        periods["5Y"] = 4  # 5 data points = 4 years of growth
    elif available_years >= 4:
        periods["5Y"] = available_years - 1

    # --- Revenue CAGR ---
    rev_series = _extract_series(
        fin,
        [
            "Total Revenue",
            "Operating Revenue",
            "Revenue From Operations",
            "Net Sales",
        ],
    )
    rev_cagrs = {}
    if rev_series is not None:
        rev_cagrs = _compute_multi_period_cagr(rev_series, periods)

    # --- PAT (Net Income) CAGR ---
    pat_series = _extract_series(
        fin,
        [
            "Net Income",
            "Net Profit",
            "PAT",
            "Profit After Tax",
        ],
    )
    pat_cagrs = {}
    if pat_series is not None:
        pat_cagrs = _compute_multi_period_cagr(pat_series, periods)

    # --- EPS CAGR (derived from Net Income / Shares Outstanding) ---
    eps_cagrs = {}
    try:
        bs = ticker.balance_sheet
        if pat_series is not None and bs is not None and not bs.empty:
            shares_series = _extract_series(
                bs,
                [
                    "Ordinary Shares Number",
                    "Share Issued",
                    "Common Stock",
                ],
            )
            if shares_series is not None:
                # Align indices
                common_idx = pat_series.index.intersection(shares_series.index)
                if len(common_idx) >= 2:
                    eps_computed = pat_series[common_idx] / shares_series[common_idx]
                    eps_computed = eps_computed.dropna()
                    if len(eps_computed) >= 2:
                        eps_cagrs = _compute_multi_period_cagr(
                            eps_computed,
                            {k: v for k, v in periods.items() if v < len(eps_computed)},
                        )
    except Exception:
        pass

    # --- CAGR Consistency Score ---
    all_cagrs = []
    for cagr_val in list(rev_cagrs.values()) + list(pat_cagrs.values()):
        if cagr_val is not None:
            all_cagrs.append(cagr_val)

    if len(all_cagrs) >= 2:
        above_15 = sum(1 for c in all_cagrs if c >= 15)
        above_10 = sum(1 for c in all_cagrs if c >= 10)

        if above_15 >= len(all_cagrs) * 0.75:
            consistency = "HIGH"
        elif above_10 >= len(all_cagrs) * 0.5:
            consistency = "MEDIUM"
        else:
            consistency = "LOW"
    else:
        consistency = "UNKNOWN"

    return {
        "Revenue_CAGR_3Y": rev_cagrs.get("3Y"),
        "Revenue_CAGR_5Y": rev_cagrs.get("5Y"),
        "PAT_CAGR_3Y": pat_cagrs.get("3Y"),
        "PAT_CAGR_5Y": pat_cagrs.get("5Y"),
        "EPS_CAGR_3Y": eps_cagrs.get("3Y"),
        "EPS_CAGR_5Y": eps_cagrs.get("5Y"),
        "CAGR_Consistency": consistency,
    }


def classify_market_cap(market_cap_crore: float) -> str:
    """
    Classify stock into market cap category based on SEBI definitions.

    SEBI (2024):
      Large Cap: Top 100 by market cap (roughly > 20,000 Cr)
      Mid Cap:   101-250 by market cap (roughly 5,000 - 20,000 Cr)
      Small Cap: 251+ by market cap (roughly < 5,000 Cr)
      Micro Cap: < 500 Cr (industry convention)
    """
    if market_cap_crore >= 20000:
        return "Large Cap"
    elif market_cap_crore >= 5000:
        return "Mid Cap"
    elif market_cap_crore >= 500:
        return "Small Cap"
    else:
        return "Micro Cap"


def extract_dividend_metrics(info: dict) -> dict[str, float | None]:
    """
    Extract dividend yield and payout ratio from yfinance info dict.

    Returns:
        {
            "Dividend_Yield": 2.5,       # percentage
            "Dividend_Payout": 35.0,     # percentage of earnings paid as dividend
        }
    """
    div_yield = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
    if div_yield is not None and div_yield > 0:
        # yfinance returns as decimal (0.025 for 2.5%)
        div_yield = round(div_yield * 100, 2) if div_yield < 1.0 else round(div_yield, 2)
        # Sanity cap: no Indian stock yields > 25% realistically
        # If above 25%, likely a data error (e.g., special dividend or wrong format)
        if div_yield > 25.0:
            div_yield = round(div_yield / 100, 2)  # Likely was already in pct
    else:
        div_yield = 0.0

    payout = info.get("payoutRatio")
    if payout is not None and payout > 0:
        payout = round(payout * 100, 2) if payout < 1.0 else round(payout, 2)
        # Cap absurd payout ratios (some data errors show > 200%)
        payout = min(payout, 200.0)
    else:
        payout = 0.0

    return {
        "Dividend_Yield": div_yield,
        "Dividend_Payout": payout,
    }
