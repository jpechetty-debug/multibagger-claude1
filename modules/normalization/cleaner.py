# modules/normalization/cleaner.py
from typing import Any, Dict, Optional, List
import logging
import numpy as np

logger = logging.getLogger(__name__)

_FUNDAMENTAL_KEYS = (
    "marketCap",
    "trailingPE",
    "returnOnEquity",
    "debtToEquity",
    "revenueGrowth",
    "earningsGrowth",
    "sector",
    "industry",
)

def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True

def _is_missing_or_zero(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        return text in {"", "none", "nan", "na", "null", "0", "0.0"}
    try:
        num = float(value)
        return num == 0.0
    except Exception:
        return False

def _fundamental_coverage(info: Any) -> int:
    if not isinstance(info, dict):
        return 0
    covered = 0
    for key in _FUNDAMENTAL_KEYS:
        value = info.get(key)
        if key in {"marketCap", "trailingPE"}:
            if _is_missing_or_zero(value):
                continue
        elif not _has_value(value):
            continue
        covered += 1
    return covered

def is_payload_skeletal(payload: Any, *, min_coverage: int = 3) -> bool:
    if not isinstance(payload, dict):
        return True
    
    price = payload.get("price")
    if price is None:
        return True
    
    try:
        price_val = float(price)
        if price_val <= 0:
            return True
    except (ValueError, TypeError):
        return True

    info = payload.get("info", {})
    if not isinstance(info, dict) or not info:
        return True

    if _is_missing_or_zero(info.get("marketCap")) or not _has_value(info.get("sector")):
        return True

    coverage = _fundamental_coverage(info)
    return coverage < int(min_coverage)

def normalize_info(
    primary_info: Optional[Dict[str, Any]],
    *,
    fallback_info: Optional[Dict[str, Any]] = None,
    alias_map: Optional[Dict[str, tuple]] = None,
) -> Dict[str, Any]:
    """Build canonical info dict using provider payload + yfinance fallback."""
    normalized: Dict[str, Any] = {}
    if isinstance(fallback_info, dict):
        for key, value in fallback_info.items():
            if _has_value(value):
                normalized[key] = value
    if isinstance(primary_info, dict):
        for key, value in primary_info.items():
            if _has_value(value):
                normalized[key] = value
    if alias_map and isinstance(primary_info, dict):
        for target, aliases in alias_map.items():
            if _has_value(normalized.get(target)):
                continue
            for alias in aliases:
                candidate = primary_info.get(alias)
                if _has_value(candidate):
                    normalized[target] = candidate
                    break
    return normalized

def json_safe_clean(obj):
    if isinstance(obj, list): return [json_safe_clean(x) for x in obj]
    if isinstance(obj, dict): return {k: json_safe_clean(v) for k, v in obj.items()}
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj): return None
    return obj
