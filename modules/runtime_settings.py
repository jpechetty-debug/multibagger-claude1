from __future__ import annotations

import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class RuntimeSettings:
    sqlite_busy_timeout_ms: int
    sqlite_write_retries: int
    sqlite_retry_base_seconds: float
    blocking_io_concurrency: int
    ticker_io_concurrency: int
    regime_cache_ttl_seconds: int
    movers_cache_ttl_seconds: int
    audit_cache_ttl_seconds: int
    embed_price_updater_in_web: bool
    embed_weekly_audit_in_web: bool
    price_update_batch_size: int
    price_update_startup_delay_seconds: int
    price_update_batch_pause_seconds: float
    price_update_interval_seconds: int
    weekly_audit_stale_after_days: int
    weekly_audit_poll_interval_seconds: int


def load_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        sqlite_busy_timeout_ms=_get_int("SQLITE_BUSY_TIMEOUT_MS", 5000),
        sqlite_write_retries=_get_int("SQLITE_WRITE_RETRIES", 5),
        sqlite_retry_base_seconds=_get_float("SQLITE_RETRY_BASE_SECONDS", 0.05),
        blocking_io_concurrency=_get_int("BLOCKING_IO_CONCURRENCY", 32),
        ticker_io_concurrency=_get_int("TICKER_IO_CONCURRENCY", 10),
        regime_cache_ttl_seconds=_get_int("REGIME_CACHE_TTL_SECONDS", 120),
        movers_cache_ttl_seconds=_get_int("MOVERS_CACHE_TTL_SECONDS", 120),
        audit_cache_ttl_seconds=_get_int("AUDIT_CACHE_TTL_SECONDS", 3600),
        embed_price_updater_in_web=_get_bool("EMBED_PRICE_UPDATER_IN_WEB", False),
        embed_weekly_audit_in_web=_get_bool("EMBED_WEEKLY_AUDIT_IN_WEB", False),
        price_update_batch_size=_get_int("PRICE_UPDATE_BATCH_SIZE", 50),
        price_update_startup_delay_seconds=_get_int("PRICE_UPDATE_STARTUP_DELAY_SECONDS", 10),
        price_update_batch_pause_seconds=_get_float("PRICE_UPDATE_BATCH_PAUSE_SECONDS", 1.0),
        price_update_interval_seconds=_get_int("PRICE_UPDATE_INTERVAL_SECONDS", 300),
        weekly_audit_stale_after_days=_get_int("WEEKLY_AUDIT_STALE_AFTER_DAYS", 7),
        weekly_audit_poll_interval_seconds=_get_int("WEEKLY_AUDIT_POLL_INTERVAL_SECONDS", 6 * 3600),
    )


runtime_settings = load_runtime_settings()
