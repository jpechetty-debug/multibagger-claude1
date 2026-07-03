"""
modules.scoring — Institutional Scoring Engine (sub-package).

Public API re-exports. All existing imports like:
    from modules.scoring import calculate_institutional_score
    from modules.scoring import normalize_metric, calculate_sector_medians
continue to work unchanged.
"""

from .adjustments import (
    _apply_optional_intel_adjustments,
    _apply_penalty_rules,
    _apply_sector_relative_adjustment,
    _calculate_bonus_total,
)
from .ceiling import (
    _apply_checklist_gate,
    _apply_score_ceiling_rules,
    _apply_spline_cap,
)
from .engine import calculate_institutional_score
from .factors import (
    _build_factor_state,
    _calculate_base_score,
    _calculate_roe_metrics,
    _calculate_sentiment_factor,
    _get_available_factors,
    _resolve_mode_and_weights,
)
from .normalization import (
    FactorState,
    _Number,
    _SectorMedians,
    _StockData,
    calculate_sector_medians,
    normalize_metric,
)

__all__ = [
    # Core public API
    "calculate_institutional_score",
    "normalize_metric",
    "calculate_sector_medians",
    "FactorState",
    # Type aliases
    "_Number",
    "_StockData",
    "_SectorMedians",
    # Factor internals (used by tests/diagnostics)
    "_resolve_mode_and_weights",
    "_calculate_sentiment_factor",
    "_calculate_roe_metrics",
    "_build_factor_state",
    "_get_available_factors",
    "_calculate_base_score",
    # Adjustment internals
    "_apply_sector_relative_adjustment",
    "_calculate_bonus_total",
    "_apply_penalty_rules",
    "_apply_optional_intel_adjustments",
    # Ceiling internals
    "_apply_spline_cap",
    "_apply_score_ceiling_rules",
    "_apply_checklist_gate",
]
