# modules/dq_gates.py
"""
Sovereign AI — Data Quality Gates

Centralized physical-limit validators for all financial metrics.
Replaces scattered inline .clip() calls with a single pass that
validates, clamps, and flags every metric entering the database.

Supports sector-aware limits loaded from the dq_sector_limits DB table
with lazy caching. Falls back to flat METRIC_LIMITS for unknown sectors.
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

# Build a quick lookup from column name to default MetricLimit
_DEFAULT_LIMITS_MAP: dict[str, MetricLimit] = {lim.column: lim for lim in METRIC_LIMITS}

# ── Sector-Aware Limit Cache ──────────────────────────────────────────────────

# Keyed by sector name → {metric_column → MetricLimit}
_sector_limits_cache: dict[str, dict[str, MetricLimit]] = {}
_cache_loaded: bool = False


def _normalise_sector_key(sector: str | None) -> str:
    """Collapse provider-specific sector labels to seeded DQ sector keys."""
    if not sector:
        return ""
    text = str(sector).strip()
    lowered = text.lower()

    if "bank" in lowered:
        return "Banking"
    if "nbfc" in lowered or "finance" in lowered or "financial" in lowered:
        return "NBFC"
    if "information technology" in lowered or "it service" in lowered or lowered == "it":
        return "IT"
    if "fmcg" in lowered or "fast moving" in lowered or "consumer goods" in lowered:
        return "FMCG"
    if "pharma" in lowered or "health" in lowered or "drug" in lowered:
        return "Pharma"
    if "metal" in lowered or "steel" in lowered or "mining" in lowered:
        return "Metals"
    if "energy" in lowered or "power" in lowered or "utilities" in lowered or "o2c" in lowered:
        return "Energy"
    if "auto" in lowered or "automobile" in lowered:
        return "Auto"
    if "real" in lowered:
        return "Realty"
    if "chemical" in lowered:
        return "Chemicals"
    if "infra" in lowered or "construction" in lowered:
        return "Infra"
    if "aviation" in lowered or "airline" in lowered:
        return "Aviation"
    if "telecom" in lowered or "communication" in lowered:
        return "Telecom"
    if "cement" in lowered:
        return "Cement"
    if "textile" in lowered or "apparel" in lowered:
        return "Textiles"
    return text


def load_sector_limits() -> None:
    """Load sector-specific limits from the dq_sector_limits DB table.

    Populates ``_sector_limits_cache`` and sets ``_cache_loaded``.
    Safe to call multiple times — only loads on first invocation.
    If the DB is unavailable, logs a warning and leaves the cache empty
    (all validation falls back to flat METRIC_LIMITS).
    """
    global _sector_limits_cache, _cache_loaded
    if _cache_loaded:
        return

    try:
        from db.repository import get_connection, _table_exists

        conn = get_connection()
        try:
            if not _table_exists(conn, "dq_sector_limits"):
                _cache_loaded = True
                return

            rows = conn.execute(
                "SELECT sector, metric, min_val, max_val, auto_scale_threshold "
                "FROM dq_sector_limits"
            ).fetchall()

            for sector, metric, min_val, max_val, auto_scale in rows:
                sector_key = _normalise_sector_key(sector)
                if sector_key not in _sector_limits_cache:
                    _sector_limits_cache[sector_key] = {}
                _sector_limits_cache[sector_key][metric] = MetricLimit(
                    column=metric,
                    min_val=float(min_val),
                    max_val=float(max_val),
                    auto_scale_threshold=float(auto_scale) if auto_scale is not None else None,
                )

            if _sector_limits_cache:
                logger.debug(
                    "Loaded sector DQ limits for %d sectors: %s",
                    len(_sector_limits_cache),
                    ", ".join(sorted(_sector_limits_cache.keys())),
                )
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("Could not load sector DQ limits from DB: %s", exc)

    _cache_loaded = True


def _get_limit_for(column: str, sector: str | None = None) -> MetricLimit | None:
    """Return the MetricLimit for a column, using sector override if available."""
    sector_key = _normalise_sector_key(sector)
    if sector_key and sector_key in _sector_limits_cache:
        sector_overrides = _sector_limits_cache[sector_key]
        if column in sector_overrides:
            return sector_overrides[column]
    return _DEFAULT_LIMITS_MAP.get(column)


def clear_sector_cache() -> None:
    """Reset the sector limits cache. Useful for tests."""
    global _sector_limits_cache, _cache_loaded
    _sector_limits_cache = {}
    _cache_loaded = False


# ── Single-Record Validation ─────────────────────────────────────────────────


def validate_record(row: dict, sector: str | None = None) -> tuple[dict, list[str]]:
    """Validate and sanitize a single data record.

    Args:
        row: The data record to validate.
        sector: Optional sector name for sector-specific limits.

    Returns:
        (sanitized_row, dq_flags) — The cleaned row and a list of
        violation tags like "pe_ratio_clamped", "dividend_yield_scaled".
    """
    # Ensure sector limits are loaded
    load_sector_limits()

    sanitized = dict(row)
    flags: list[str] = []

    for default_limit in METRIC_LIMITS:
        col = default_limit.column
        value = sanitized.get(col)
        if value is None:
            continue

        # Use sector-specific limit if available, else flat default
        limit = _get_limit_for(col, sector)
        if limit is None:
            continue

        try:
            val = float(value)
        except (TypeError, ValueError):
            sanitized[col] = None
            flags.append(f"{col}_unparseable")
            continue

        if not math.isfinite(val):
            sanitized[col] = None
            flags.append(f"{col}_non_finite")
            continue

        # Auto-scale check (e.g., dividend yield 250 → 2.5)
        if limit.auto_scale_threshold is not None and val > limit.auto_scale_threshold:
            val = val / 100.0
            flags.append(f"{col}_auto_scaled")

        # Clamp to physical limits
        if val < limit.min_val:
            val = limit.min_val
            flags.append(f"{col}_clamped_low")
        elif val > limit.max_val:
            val = limit.max_val
            flags.append(f"{col}_clamped_high")

        sanitized[col] = val

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


def _deduplicate_flags(flags_str: str) -> str:
    """Deduplicate a comma-separated flags string, preserving order."""
    if not flags_str:
        return ""
    seen = set()
    ordered = []
    for p in str(flags_str).split(","):
        p_clean = p.strip()
        if p_clean and p_clean not in seen:
            seen.add(p_clean)
            ordered.append(p_clean)
    return ",".join(ordered)


def _clean_managed_flags(flags_str: str) -> str:
    """Remove any flags managed by the DQ gates from the comma-separated string, preserving order and uniqueness."""
    if not flags_str or flags_str == "nan":
        return ""
    managed_suffixes = ("_invalid", "_unparseable", "_non_finite", "_auto_scaled", "_clamped_low", "_clamped_high")
    seen = set()
    ordered = []
    for p in str(flags_str).split(","):
        p_clean = p.strip()
        if p_clean and p_clean not in seen:
            if not p_clean.endswith(managed_suffixes):
                seen.add(p_clean)
                ordered.append(p_clean)
    return ",".join(ordered)


def _append_flag(existing_flags: str, new_flag: str) -> str:
    """Append a flag to a comma-separated list of flags without introducing duplicates."""
    if existing_flags is None:
        return new_flag
    existing_str = _deduplicate_flags(existing_flags)
    if not existing_str or existing_str == "nan":
        return new_flag
    parts = [p.strip() for p in existing_str.split(",") if p.strip()]
    if new_flag not in parts:
        parts.append(new_flag)
    return ",".join(parts)


def validate_dataframe(df):
    """Apply DQ gates to every row in a pandas DataFrame.

    Mutates the DataFrame in-place using vectorized operations:
    - Clamps/scales columns that violate physical limits.
    - Populates a ``data_quality`` column with a 0-100 score.
    - If a ``sector`` column is present, applies sector-specific limits.

    Returns the DataFrame for chaining.
    """
    import numpy as np
    import pandas as pd

    # Ensure sector limits are loaded
    load_sector_limits()

    all_limit_columns = [lim.column for lim in METRIC_LIMITS]
    present_columns = [c for c in all_limit_columns if c in df.columns]

    if not present_columns:
        return df

    total_fields = len(present_columns)
    penalties = pd.Series(0.0, index=df.index)
    # Track flags for reporting (as comma-separated strings), preserving existing flags
    if "data_quality_flags" not in df.columns:
        df["data_quality_flags"] = ""
    else:
        df["data_quality_flags"] = df["data_quality_flags"].fillna("").astype(str).apply(_clean_managed_flags)

    has_sector = "sector" in df.columns and bool(_sector_limits_cache)

    for default_limit in METRIC_LIMITS:
        col = default_limit.column
        if col not in df.columns:
            continue

        originally_nan = df[col].isna()
        # Ensure numeric and handle unparseable/non_finite
        df[col] = pd.to_numeric(df[col], errors="coerce")
        # Non-finite values will also be NaN after coerce + replace
        df[col] = df[col].replace([np.inf, -np.inf], np.nan)
        mask_nan = df[col].isna()
        penalties[mask_nan] += 1

        # Only flag unparseable values (values that were NOT originally NaN, but became NaN)
        mask_unparseable = mask_nan & ~originally_nan
        if mask_unparseable.any():
            df.loc[mask_unparseable, "data_quality_flags"] = df.loc[mask_unparseable, "data_quality_flags"].apply(
                lambda x, col=col: _append_flag(x, f"{col}_invalid")
            )

        if has_sector:
            # Sector-aware path: apply per-sector limits
            _apply_sector_aware_limits(df, col, default_limit, mask_nan, penalties)
        else:
            # Flat path: apply global limits (original behavior)
            _apply_flat_limits(df, col, default_limit, mask_nan, penalties)

    if penalties.sum() > 0:
        logger.debug("DQ gates applied. Total flags: %d", int(penalties.sum()))

    penalty_per_flag = 100.0 / max(total_fields, 1)
    df["data_quality"] = (100.0 - penalties * penalty_per_flag).clip(lower=0.0).round(1)

    # Penalize mock history by 50 points if present
    mock_mask = df["data_quality_flags"].str.contains("mock_history", na=False)
    if mock_mask.any():
        df.loc[mock_mask, "data_quality"] = (df.loc[mock_mask, "data_quality"] - 50.0).clip(lower=0.0)

    return df


def _apply_flat_limits(df, col: str, limit: MetricLimit, mask_nan, penalties):
    """Apply a single MetricLimit to the entire column (no sector awareness)."""
    # Auto-scale check
    if limit.auto_scale_threshold is not None:
        mask_scale = (df[col] > limit.auto_scale_threshold) & ~mask_nan
        if mask_scale.any():
            df.loc[mask_scale, col] = df.loc[mask_scale, col] / 100.0
            penalties[mask_scale] += 1
            df.loc[mask_scale, "data_quality_flags"] = df.loc[mask_scale, "data_quality_flags"].apply(
                lambda x, col=col: _append_flag(x, f"{col}_auto_scaled")
            )

    # Clamp low
    mask_low = (df[col] < limit.min_val) & ~mask_nan
    if mask_low.any():
        df.loc[mask_low, col] = limit.min_val
        penalties[mask_low] += 1
        df.loc[mask_low, "data_quality_flags"] = df.loc[mask_low, "data_quality_flags"].apply(
            lambda x, col=col: _append_flag(x, f"{col}_clamped_low")
        )

    # Clamp high
    mask_high = (df[col] > limit.max_val) & ~mask_nan
    if mask_high.any():
        df.loc[mask_high, col] = limit.max_val
        penalties[mask_high] += 1
        df.loc[mask_high, "data_quality_flags"] = df.loc[mask_high, "data_quality_flags"].apply(
            lambda x, col=col: _append_flag(x, f"{col}_clamped_high")
        )


def _apply_sector_aware_limits(df, col: str, default_limit: MetricLimit, mask_nan, penalties):
    """Apply limits per-sector, falling back to the default for unknown sectors."""
    import numpy as np

    # Collect unique sectors present in the DataFrame
    sectors_in_df = df["sector"].fillna("").unique()

    for sector_val in sectors_in_df:
        # Rows belonging to this sector
        if sector_val:
            sector_mask = (df["sector"] == sector_val) & ~mask_nan
        else:
            sector_mask = (df["sector"].isna() | (df["sector"] == "")) & ~mask_nan

        if not sector_mask.any():
            continue

        # Resolve the limit: sector override if available, else default
        limit = _get_limit_for(col, sector_val if sector_val else None)
        if limit is None:
            limit = default_limit

        # Auto-scale check
        if limit.auto_scale_threshold is not None:
            mask_scale = sector_mask & (df[col] > limit.auto_scale_threshold)
            if mask_scale.any():
                df.loc[mask_scale, col] = df.loc[mask_scale, col] / 100.0
                penalties[mask_scale] += 1
                df.loc[mask_scale, "data_quality_flags"] = df.loc[mask_scale, "data_quality_flags"].apply(
                    lambda x, col=col: _append_flag(x, f"{col}_auto_scaled")
                )

        # Clamp low
        mask_low = sector_mask & (df[col] < limit.min_val)
        if mask_low.any():
            df.loc[mask_low, col] = limit.min_val
            penalties[mask_low] += 1
            df.loc[mask_low, "data_quality_flags"] = df.loc[mask_low, "data_quality_flags"].apply(
                lambda x, col=col: _append_flag(x, f"{col}_clamped_low")
            )

        # Clamp high
        mask_high = sector_mask & (df[col] > limit.max_val)
        if mask_high.any():
            df.loc[mask_high, col] = limit.max_val
            penalties[mask_high] += 1
            df.loc[mask_high, "data_quality_flags"] = df.loc[mask_high, "data_quality_flags"].apply(
                lambda x, col=col: _append_flag(x, f"{col}_clamped_high")
            )
