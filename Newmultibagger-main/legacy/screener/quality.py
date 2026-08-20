"""
Data quality scoring for screened stocks.

Extracted from scripts/internal/screener.py.
Handles completeness scoring, source confidence, freshness, and DQ flags.
"""

import numpy as np
from modules.data_layer.dq_gates import _append_flag


# --- Constants ---

_DATA_QUALITY_FIELDS = [
    "PE_Ratio", "PEG_Ratio", "ROE%", "Avg_ROE_5Y%", "Debt_Equity",
    "EPS_Growth%", "Sales_Growth_5Y%", "CFO_PAT_Ratio", "F_Score", "Market_Cap_Cr",
]

_DATA_QUALITY_WEIGHTS = {
    "PE_Ratio": 12, "PEG_Ratio": 6, "ROE%": 12, "Avg_ROE_5Y%": 10,
    "Debt_Equity": 8, "EPS_Growth%": 10, "Sales_Growth_5Y%": 12,
    "CFO_PAT_Ratio": 12, "F_Score": 8, "Market_Cap_Cr": 10,
}

_SOURCE_CONFIDENCE = {
    "pnsea": 1.00, "nsepython": 0.90, "yfinance": 0.75,
    "fallback_failed": 0.30, "unknown": 0.55,
}


# --- Helpers ---

def _is_missing_info_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not bool(value.strip())
    if isinstance(value, list | tuple | set | dict):
        return len(value) == 0
    return False


def _is_finite_number(value):
    if value is None:
        return False
    if isinstance(value, int | float | np.floating):
        return np.isfinite(value)
    try:
        parsed = float(value)
        return np.isfinite(parsed)
    except Exception:
        return False


def _is_present_metric(value):
    if not _is_finite_number(value):
        return False
    return float(value) != 0.0


def _finite_or_default(value, default=0.0):
    if not _is_finite_number(value):
        return default
    return float(value)


def _compute_smart_money_pct(promoter_holding, inst_holding) -> float:
    return (promoter_holding or 0.0) + (inst_holding or 0.0)


def _freshness_score(price_age_days):
    if price_age_days is None:
        return 20.0
    if price_age_days <= 1:
        return 100.0
    if price_age_days <= 3:
        return 85.0
    if price_age_days <= 7:
        return 65.0
    if price_age_days <= 14:
        return 45.0
    return 20.0


def _merge_data_quality_flags(existing_flags: str, raw_flags) -> str:
    if not raw_flags:
        return existing_flags or ""
    if isinstance(raw_flags, (list, tuple, set)):
        tokens = [str(f).strip() for f in raw_flags if str(f).strip()]
    else:
        tokens = [p.strip() for p in str(raw_flags).split(",") if p.strip()]
    merged = existing_flags or ""
    for token in tokens:
        merged = _append_flag(merged, token)
    return merged


# --- Main DQ Scorer ---

def calculate_data_quality(data, *, zero_valuation_cap=20.0):
    """Weighted data quality score (0-100): completeness + source confidence + freshness."""
    flags = data.get("_dq_flags")
    if not isinstance(flags, dict):
        flags = {field: _is_present_metric(data.get(field)) for field in _DATA_QUALITY_FIELDS}

    total_weight = float(sum(_DATA_QUALITY_WEIGHTS.values()) or 100.0)
    completeness_points = 0.0
    for f_name in _DATA_QUALITY_FIELDS:
        if bool(flags.get(f_name, False)):
            completeness_points += float(_DATA_QUALITY_WEIGHTS.get(f_name, 0))
    completeness_score = (completeness_points / total_weight) * 100.0

    source = str(data.get("Data_Source", "unknown")).strip().lower()
    source_score = float(_SOURCE_CONFIDENCE.get(source, _SOURCE_CONFIDENCE["unknown"])) * 100.0

    price_age_days = data.get("Price_Age_Days")
    try:
        price_age_days = int(price_age_days) if price_age_days is not None else None
    except Exception:
        price_age_days = None
    freshness = _freshness_score(price_age_days)

    final = (0.70 * completeness_score) + (0.20 * source_score) + (0.10 * freshness)
    valuation_missing = not _is_present_metric(
        data.get("Market_Cap_Cr")
    ) and not _is_present_metric(data.get("PE_Ratio"))
    if valuation_missing:
        final = min(final, float(zero_valuation_cap))
    data["_dq_breakdown"] = {
        "completeness_score": round(completeness_score, 1),
        "source_score": round(source_score, 1),
        "freshness_score": round(freshness, 1),
        "zero_valuation_block": bool(valuation_missing),
    }
    data["_dq_blocked"] = bool(valuation_missing)
    return round(max(0.0, min(100.0, final)), 1)
