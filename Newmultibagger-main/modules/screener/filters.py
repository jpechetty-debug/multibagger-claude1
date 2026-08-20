"""
Data filtering and validation helpers for screened stocks.

Extracted from scripts/internal/screener.py.
Handles info backfill, debt/equity resolution, book value resolution.
"""

from modules.screener.quality import _is_finite_number, _is_present_metric, _is_missing_info_value


_INFO_BACKFILL_KEYS = [
    "marketCap", "trailingPE", "returnOnEquity", "debtToEquity",
    "earningsGrowth", "revenueGrowth", "bookValue", "trailingEps",
    "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "sector", "industry",
]

_FETCH_CORE_FIELDS = [
    "Market_Cap_Cr", "PE_Ratio", "ROE%", "Debt_Equity",
    "Sales_Growth_TTM%", "CFO_PAT_Ratio",
]

_FETCH_CORE_FLAG_FIELDS = [
    "Market_Cap_Cr", "PE_Ratio", "ROE%", "F_Score",
    "Debt_Equity", "Sales_Growth_5Y%", "EPS_Growth%", "CFO_PAT_Ratio",
]


def _needs_info_backfill(info):
    if not isinstance(info, dict) or not info:
        return True
    if _is_missing_info_value(info.get("marketCap")):
        return True
    missing = sum(1 for key in _INFO_BACKFILL_KEYS if _is_missing_info_value(info.get(key)))
    return missing >= 5


def _merge_info(primary_info, fallback_info):
    merged = {}
    if isinstance(fallback_info, dict):
        for key, value in fallback_info.items():
            if not _is_missing_info_value(value):
                merged[key] = value
    if isinstance(primary_info, dict):
        for key, value in primary_info.items():
            if not _is_missing_info_value(value):
                merged[key] = value
    if _is_missing_info_value(merged.get("sector")) and not _is_missing_info_value(
        merged.get("industry")
    ):
        merged["sector"] = merged.get("industry")
    return merged


def _resolve_debt_equity(raw: dict, info: dict) -> float:
    """Resolve Debt/Equity as a clean ratio (e.g. 0.35 for D/E of 35%).

    Prefers canonical source's Debt_Equity over yfinance's debtToEquity.
    """
    canonical = raw.get("Debt_Equity")
    if _is_finite_number(canonical):
        return float(canonical)
    raw_de = info.get("debtToEquity", 0) or 0
    if raw_de > 10:
        raw_de = raw_de / 100.0
    return float(raw_de)


def _resolve_book_value(raw: dict, info: dict) -> float:
    """Resolve Book Value per share, preferring canonical source over yfinance."""
    canonical = raw.get("Book_Value")
    if _is_present_metric(canonical):
        return float(canonical)
    return info.get("bookValue", 0) or 0
