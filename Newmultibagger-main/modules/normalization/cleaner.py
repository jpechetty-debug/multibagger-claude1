# modules/normalization/cleaner.py
from core.observability.logger import get_logger
from typing import Any

import numpy as np
_log = get_logger(__name__)


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
    if isinstance(value, list | tuple | set | dict):
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
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
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
    primary_info: dict[str, Any] | None,
    *,
    fallback_info: dict[str, Any] | None = None,
    alias_map: dict[str, tuple] | None = None,
) -> dict[str, Any]:
    """Build canonical info dict using provider payload + yfinance fallback.

    Resolution order:
    1. Populate from fallback_info (lowest priority)
    2. Resolve aliased canonical fields using resolve_key (with conflict logging)
    3. Copy remaining non-aliased keys from primary_info (passthrough)

    This order ensures the alias map always wins over raw key passthrough —
    i.e. if the raw dict has both `revenueGrowth` and `salesGrowth`, the alias
    map decides which one becomes the canonical `revenueGrowth` value, rather
    than the raw copy blindly picking whichever key happens to match the target.
    """
    normalized: dict[str, Any] = {}

    # Step 1: fallback (lowest priority)
    if isinstance(fallback_info, dict):
        for key, value in fallback_info.items():
            if _has_value(value):
                normalized[key] = value

    # Step 2: alias-map resolution (runs before raw copy so it takes precedence)
    aliased_targets: set[str] = set()
    if alias_map and isinstance(primary_info, dict):
        from modules.adapters.base import resolve_key
        source = primary_info.get("_source", "unknown")
        for target, aliases in alias_map.items():
            aliased_targets.add(target)
            if _has_value(normalized.get(target)):
                continue
            value = resolve_key(
                primary_info,
                candidates=aliases if isinstance(aliases, tuple) else tuple(aliases),
                source=source,
                field=target,
            )
            if _has_value(value):
                normalized[target] = value

    # Step 3: copy remaining primary_info keys (non-aliased passthrough)
    if isinstance(primary_info, dict):
        for key, value in primary_info.items():
            if key == "_source":
                continue           # internal tag — never leak into output
            if key in aliased_targets:
                continue           # already resolved by alias map
            if _has_value(value):
                normalized[key] = value

    return normalized


def json_safe_clean(obj):
    if isinstance(obj, list):
        return [json_safe_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: json_safe_clean(v) for k, v in obj.items()}
    if isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj
