# modules/dq_gates.py
"""
Sovereign AI — Data Quality Gates

Centralized physical-limit validators for all financial metrics.
Replaces scattered inline .clip() calls with a single pass that
validates, clamps, and flags every metric entering the database.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Physical Limit Definitions ────────────────────────────────────────────────


@dataclass(frozen=True)
class MetricLimit:
    column: str
    min_val: float
    max_val: float
    auto_scale_threshold: float | None = None  # If value > threshold, divide by 100


METRIC_LIMITS: list[MetricLimit] = [
    MetricLimit("pe_ratio", -100, 1000),
    MetricLimit("roe", -500, 500),
    MetricLimit("score", 0, 100),
    MetricLimit("debt_equity", 0, 50),
    MetricLimit("market_cap_cr", 0, 5_000_000),
    MetricLimit("cfo_pat_ratio", -10, 20),
    MetricLimit("dividend_yield", 0, 25, auto_scale_threshold=25),
    MetricLimit("dividend_payout", 0, 200),
    MetricLimit("avg_roe_5y", -500, 500),
    MetricLimit("sales_cagr_5y", -100, 500),
    MetricLimit("ret_1m", -1, 10),
    MetricLimit("ret_3m", -1, 10),
    MetricLimit("ret_6m", -1, 20),
]


# ── Single-Record Validation ─────────────────────────────────────────────────


def validate_record(row: dict) -> tuple[dict, list[str]]:
    """Validate and sanitize a single data record.

    Returns:
        (sanitized_row, dq_flags) — The cleaned row and a list of
        violation tags like "pe_ratio_clamped", "dividend_yield_scaled".
    """
    sanitized = dict(row)
    flags: list[str] = []

    for limit in METRIC_LIMITS:
        value = sanitized.get(limit.column)
        if value is None:
            continue

        try:
            val = float(value)
        except (TypeError, ValueError):
            sanitized[limit.column] = None
            flags.append(f"{limit.column}_unparseable")
            continue

        if not math.isfinite(val):
            sanitized[limit.column] = None
            flags.append(f"{limit.column}_non_finite")
            continue

        # Auto-scale check (e.g., dividend yield 250 → 2.5)
        if limit.auto_scale_threshold is not None and val > limit.auto_scale_threshold:
            val = val / 100.0
            flags.append(f"{limit.column}_auto_scaled")

        # Clamp to physical limits
        if val < limit.min_val:
            val = limit.min_val
            flags.append(f"{limit.column}_clamped_low")
        elif val > limit.max_val:
            val = limit.max_val
            flags.append(f"{limit.column}_clamped_high")

        sanitized[limit.column] = val

    return sanitized, flags


def compute_data_quality_score(flags: list[str], total_fields: int) -> float:
    """Compute a 0-100 data quality score.

    Each flag reduces the score proportionally.  A record with zero
    flags scores 100;  one with flags on every field scores 0.
    """
    if total_fields <= 0:
        return 0.0
    penalty_per_flag = 100.0 / max(total_fields, 1)
    score = max(0.0, 100.0 - len(flags) * penalty_per_flag)
    return round(score, 1)


# ── DataFrame-Level Validation ────────────────────────────────────────────────


def validate_dataframe(df):
    """Apply DQ gates to every row in a pandas DataFrame.

    Mutates the DataFrame in-place:
    - Clamps/scales columns that violate physical limits.
    - Populates a ``data_quality`` column with a 0-100 score.

    Returns the DataFrame for chaining.
    """
    import pandas as pd

    all_limit_columns = [lim.column for lim in METRIC_LIMITS]
    present_columns = [c for c in all_limit_columns if c in df.columns]

    if not present_columns:
        return df

    total_fields = len(present_columns)
    quality_scores: list[float] = []

    for idx in df.index:
        row_dict = {col: df.at[idx, col] for col in present_columns}
        sanitized, flags = validate_record(row_dict)

        # Write back sanitized values
        for col in present_columns:
            df.at[idx, col] = sanitized.get(col)

        if flags:
            symbol = df.at[idx, "symbol"] if "symbol" in df.columns else idx
            logger.debug("DQ flags for %s: %s", symbol, flags)

        quality_scores.append(compute_data_quality_score(flags, total_fields))

    df["data_quality"] = quality_scores
    return df
