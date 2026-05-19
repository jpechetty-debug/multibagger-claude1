# modules/dq_gates.py
"""
Sovereign AI — Data Quality Gates

Centralized physical-limit validators for all financial metrics.
Replaces scattered inline .clip() calls with a single pass that
validates, clamps, and flags every metric entering the database.
"""

from __future__ import annotations

from modules.structured_logger import SovereignLogger

import math
from dataclasses import dataclass, field

_sov = SovereignLogger("dq_gates")
logger = _sov.logger

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
    # Phase 1.2: Fields used by scoring engine that were previously unchecked
    MetricLimit("eps_growth", -500, 1000),
    MetricLimit("promoter_holding", 0, 100),
    MetricLimit("inst_holding", 0, 100),
    MetricLimit("f_score", 0, 9),
    MetricLimit("peg_ratio", -50, 100),
    MetricLimit("value_gap", -200, 500),
    MetricLimit("atr", 0, 100_000),
    MetricLimit("down_from_52w_high", 0, 100),
    MetricLimit("rs_rating", 0, 10),
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

    # Phase 4.4: Per-record DQ gate logging with symbol context
    if flags:
        symbol = row.get("symbol") or row.get("Symbol") or "UNKNOWN"
        logger.debug("DQ gate activated for %s: %s", symbol, ", ".join(flags))

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

    Mutates the DataFrame in-place using vectorized operations:
    - Clamps/scales columns that violate physical limits.
    - Populates a ``data_quality`` column with a 0-100 score.

    Returns the DataFrame for chaining.
    """
    import numpy as np
    import pandas as pd

    all_limit_columns = [lim.column for lim in METRIC_LIMITS]
    present_columns = [c for c in all_limit_columns if c in df.columns]

    if not present_columns:
        return df

    total_fields = len(present_columns)
    penalties = pd.Series(0.0, index=df.index)
    # Track flags for reporting (as comma-separated strings)
    df["data_quality_flags"] = ""

    for limit in METRIC_LIMITS:
        col = limit.column
        if col not in df.columns:
            continue

        # Ensure numeric and handle unparseable/non_finite
        df[col] = pd.to_numeric(df[col], errors="coerce")
        mask_nan = df[col].isna()
        # Non-finite values will also be NaN after coerce + replace
        df[col] = df[col].replace([np.inf, -np.inf], np.nan)
        mask_nan = df[col].isna()
        penalties[mask_nan] += 1
        df.loc[mask_nan, "data_quality_flags"] = df.loc[mask_nan, "data_quality_flags"].apply(
            lambda x, col=col: (x + f",{col}_invalid" if x else f"{col}_invalid")
        )

        # Auto-scale check
        if limit.auto_scale_threshold is not None:
            mask_scale = (df[col] > limit.auto_scale_threshold) & ~mask_nan
            if mask_scale.any():
                df.loc[mask_scale, col] = df.loc[mask_scale, col] / 100.0
                penalties[mask_scale] += 1
                df.loc[mask_scale, "data_quality_flags"] = df.loc[mask_scale, "data_quality_flags"].apply(
                    lambda x, col=col: (x + f",{col}_auto_scaled" if x else f"{col}_auto_scaled")
                )

        # Clamp low
        mask_low = (df[col] < limit.min_val) & ~mask_nan
        if mask_low.any():
            df.loc[mask_low, col] = limit.min_val
            penalties[mask_low] += 1
            df.loc[mask_low, "data_quality_flags"] = df.loc[mask_low, "data_quality_flags"].apply(
                lambda x, col=col: (x + f",{col}_clamped_low" if x else f"{col}_clamped_low")
            )

        # Clamp high
        mask_high = (df[col] > limit.max_val) & ~mask_nan
        if mask_high.any():
            df.loc[mask_high, col] = limit.max_val
            penalties[mask_high] += 1
            df.loc[mask_high, "data_quality_flags"] = df.loc[mask_high, "data_quality_flags"].apply(
                lambda x, col=col: (x + f",{col}_clamped_high" if x else f"{col}_clamped_high")
            )

    if penalties.sum() > 0:
        logger.debug("DQ gates applied. Total flags: %d", int(penalties.sum()))

    penalty_per_flag = 100.0 / max(total_fields, 1)
    df["data_quality"] = (100.0 - penalties * penalty_per_flag).clip(lower=0.0).round(1)

    return df
