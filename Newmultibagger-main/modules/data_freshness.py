# modules/data_freshness.py
"""
Sovereign AI — Data Freshness & Quality Engine

Provides hard freshness rules:
  - Dashboard badges: FRESH / STALE / EXPIRED
  - BUY label blocking when data exceeds age threshold
  - Provider failure tracking (yfinance / NSE / pnsea)
  - Universe staleness alerting (>20% stale triggers alert)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from modules.db_utils import get_db_connection

# ── Freshness Thresholds (configurable via env in future) ────────────────────
FRESH_MAX_DAYS = 3
STALE_MAX_DAYS = 7
# >STALE_MAX_DAYS = EXPIRED

BUY_BLOCK_AGE_DAYS = 5  # Block BUY labels if data older than this

UNIVERSE_STALE_ALERT_PCT = 20.0  # Alert if >20% universe is stale


class FreshnessStatus(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class FreshnessReport:
    status: FreshnessStatus
    latest_as_of_date: str | None
    age_days: int
    source: str
    data_quality: float  # 0-100
    scheduled_refresh: dict[str, Any]
    universe_counts: dict[str, int]  # fresh, stale, expired


@dataclass(frozen=True)
class ProviderHealth:
    name: str
    success_rate: float
    total_calls: int
    last_success: str | None
    last_failure: str | None
    status: str  # "healthy", "degraded", "down"


@dataclass(frozen=True)
class UniverseQuality:
    total_stocks: int
    fresh_count: int
    stale_count: int
    expired_count: int
    incomplete_count: int
    stale_pct: float
    alert_active: bool
    alert_message: str | None


# ── Phase 4.5: Actual Provider Call Tracking ─────────────────────────────────

class ProviderCallTracker:
    """Tracks actual per-provider success/failure counts in SQLite.

    Usage:
        tracker = ProviderCallTracker()
        tracker.record("yfinance", success=True)
        tracker.record("yfinance", success=False, error="401 Unauthorized")
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._init_db()

    def _init_db(self):
        try:
            with _get_cache_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS provider_call_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        provider TEXT NOT NULL,
                        success INTEGER NOT NULL,
                        error_message TEXT,
                        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_provider_call_provider
                    ON provider_call_log (provider, recorded_at)
                """)
                conn.commit()
        except Exception:
            pass

    def record(self, provider: str, success: bool, error: str | None = None):
        """Record a single provider call outcome."""
        try:
            with _get_cache_connection() as conn:
                conn.execute(
                    "INSERT INTO provider_call_log (provider, success, error_message) VALUES (?, ?, ?)",
                    (provider, 1 if success else 0, error),
                )
                conn.commit()
        except Exception:
            pass

    def get_stats(self, provider: str, window_hours: int = 24) -> dict:
        """Get success/failure stats for a provider within a time window."""
        try:
            with _get_cache_connection() as conn:
                import sqlite3 as _sqlite3
                conn.row_factory = _sqlite3.Row
                cutoff = time.time() - (window_hours * 3600)
                row = conn.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successes,
                        MAX(CASE WHEN success = 1 THEN recorded_at END) as last_success,
                        MAX(CASE WHEN success = 0 THEN recorded_at END) as last_failure
                    FROM provider_call_log
                    WHERE provider = ? AND recorded_at > datetime(?, 'unixepoch')""",
                    (provider, cutoff),
                ).fetchone()
                total = row["total"] or 0
                successes = row["successes"] or 0
                return {
                    "total": total,
                    "successes": successes,
                    "success_rate": round((successes / total) * 100, 1) if total > 0 else 0.0,
                    "last_success": row["last_success"],
                    "last_failure": row["last_failure"],
                }
        except Exception:
            return {"total": 0, "successes": 0, "success_rate": 0.0, "last_success": None, "last_failure": None}

    def prune(self, keep_hours: int = 168):
        """Remove entries older than keep_hours (default: 7 days)."""
        try:
            with _get_cache_connection() as conn:
                cutoff = time.time() - (keep_hours * 3600)
                conn.execute(
                    "DELETE FROM provider_call_log WHERE recorded_at < datetime(?, 'unixepoch')",
                    (cutoff,),
                )
                conn.commit()
        except Exception:
            pass


# Module-level singleton for easy import
provider_tracker = ProviderCallTracker()


# ── Internal DB helpers ──────────────────────────────────────────────────────

def _get_stocks_connection():
    return get_db_connection("stocks.db")


def _get_cache_connection():
    return get_db_connection("data_cache.db")


def _date_age_days(date_str: str | None) -> int:
    if not date_str:
        return 999
    try:
        as_of = datetime.fromisoformat(date_str[:10]).date()
        return (date.today() - as_of).days
    except (ValueError, TypeError):
        return 999


def classify_freshness(age_days: int) -> FreshnessStatus:
    if age_days <= FRESH_MAX_DAYS:
        return FreshnessStatus.FRESH
    if age_days <= STALE_MAX_DAYS:
        return FreshnessStatus.STALE
    return FreshnessStatus.EXPIRED


def should_block_buy_label(age_days: int) -> bool:
    return age_days > BUY_BLOCK_AGE_DAYS


# ── Public API ───────────────────────────────────────────────────────────────


def get_freshness_report() -> FreshnessReport:
    """Query the database for the latest as_of_date and compute freshness."""
    try:
        with _get_stocks_connection() as conn:
            conn.row_factory = __import__("sqlite3").Row
            # Get latest as_of_date from fundamentals_pit
            row = conn.execute(
                "SELECT MAX(as_of_date) as latest_date FROM fundamentals_pit"
            ).fetchone()
            latest_date = row["latest_date"] if row else None

            # Data quality: % of stocks with non-null scores in latest snapshot
            if latest_date:
                quality_row = conn.execute(
                    """SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN score IS NOT NULL AND score > 0 THEN 1 ELSE 0 END) as scored
                    FROM fundamentals_pit WHERE as_of_date = ?""",
                    (latest_date,),
                ).fetchone()
                total = quality_row["total"] or 1
                scored = quality_row["scored"] or 0
                data_quality = round((scored / total) * 100, 1)
            else:
                data_quality = 0.0

            age = _date_age_days(latest_date)
            status = classify_freshness(age)

            # Check for scheduled refresh status
            scheduled = _get_scheduled_refresh_status(conn)

            # Calculate universe breakdown
            quality = get_universe_quality()
            universe_counts = {
                "fresh": quality.fresh_count,
                "stale": quality.stale_count,
                "expired": quality.expired_count,
                "incomplete": quality.incomplete_count,
                "total": quality.total_stocks
            }

            return FreshnessReport(
                status=status,
                latest_as_of_date=latest_date,
                age_days=age,
                source="fundamentals_pit",
                data_quality=data_quality,
                scheduled_refresh=scheduled,
                universe_counts=universe_counts,
            )
    except Exception as exc:
        return FreshnessReport(
            status=FreshnessStatus.UNKNOWN,
            latest_as_of_date=None,
            age_days=999,
            source="error",
            data_quality=0.0,
            scheduled_refresh={"status": "error", "message": str(exc)},
            universe_counts={"fresh": 0, "stale": 0, "expired": 0, "incomplete": 0, "total": 0}
        )


def _get_scheduled_refresh_status(conn) -> dict[str, Any]:
    """Check when the last scan ran and estimate next expected scan."""
    try:
        row = conn.execute("SELECT MAX(updated_at) as last_update FROM multibaggers").fetchone()
        last_update = row["last_update"] if row else None

        if last_update:
            try:
                last_dt = datetime.fromisoformat(str(last_update))
                age_hours = (datetime.now() - last_dt).total_seconds() / 3600
                return {
                    "last_scan": str(last_update),
                    "age_hours": round(age_hours, 1),
                    "status": "recent" if age_hours < 24 else "overdue",
                    "next_expected": "Within 24h (automated)"
                    if age_hours < 24
                    else "OVERDUE — manual scan recommended",
                }
            except (ValueError, TypeError):
                pass

        return {"status": "unknown", "last_scan": None}
    except Exception:
        return {"status": "unavailable"}


def get_provider_health() -> list[ProviderHealth]:
    """
    Phase 4.5: Return actual measured provider health from call log.
    Falls back to legacy cache-inference if no call log data exists.
    """
    providers_result = []
    tracker = ProviderCallTracker()

    for pname in ["yfinance", "pnsea", "nsepython"]:
        stats = tracker.get_stats(pname, window_hours=24)

        if stats["total"] > 0:
            # Actual measured data available
            rate = stats["success_rate"]
            status = "healthy" if rate > 70 else "degraded" if rate > 30 else "down"

            providers_result.append(
                ProviderHealth(
                    name=pname,
                    success_rate=rate,
                    total_calls=stats["total"],
                    last_success=stats["last_success"],
                    last_failure=stats["last_failure"],
                    status=status,
                )
            )
        else:
            # No call log data — fall back to cache-based inference
            try:
                with _get_cache_connection() as conn:
                    conn.row_factory = __import__("sqlite3").Row
                    now = time.time()
                    one_day_ago = now - 86400

                    total_row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM cache WHERE key LIKE 'fund_%'"
                    ).fetchone()
                    total = total_row["cnt"] if total_row else 0

                    recent_row = conn.execute(
                        "SELECT COUNT(*) as cnt FROM cache WHERE key LIKE 'fund_%' AND timestamp > ?",
                        (one_day_ago,),
                    ).fetchone()
                    recent = recent_row["cnt"] if recent_row else 0

                    fresh_pct = (recent / max(total, 1)) * 100
                    # Conservative estimate from cache
                    rate = min(100.0, fresh_pct * 0.8)
                    status = "healthy" if rate > 70 else "degraded" if rate > 30 else "down"

                    providers_result.append(
                        ProviderHealth(
                            name=pname,
                            success_rate=round(rate, 1),
                            total_calls=total if pname == "yfinance" else total // 3,
                            last_success=datetime.fromtimestamp(now).isoformat() if rate > 50 else None,
                            last_failure=None,
                            status=f"{status} (inferred)",
                        )
                    )
            except Exception:
                providers_result.append(
                    ProviderHealth(pname, 0.0, 0, None, None, "unknown")
                )

    return providers_result


def _default_provider_health() -> list[ProviderHealth]:
    return [
        ProviderHealth("yfinance", 0.0, 0, None, None, "unknown"),
        ProviderHealth("pnsea", 0.0, 0, None, None, "unknown"),
        ProviderHealth("nsepython", 0.0, 0, None, None, "unknown"),
    ]



def get_universe_quality() -> UniverseQuality:
    """Check what percentage of the universe has stale or incomplete fundamentals."""
    try:
        with _get_stocks_connection() as conn:
            conn.row_factory = __import__("sqlite3").Row
            latest_row = conn.execute(
                "SELECT MAX(as_of_date) as latest FROM fundamentals_pit"
            ).fetchone()
            latest_date = latest_row["latest"] if latest_row else None

            if not latest_date:
                return UniverseQuality(0, 0, 0, 0, 0, 0.0, False, None)

            latest_age = _date_age_days(latest_date)

            # Count total stocks
            total_row = conn.execute(
                "SELECT COUNT(DISTINCT symbol) as cnt FROM fundamentals_pit WHERE as_of_date = ?",
                (latest_date,),
            ).fetchone()
            total = total_row["cnt"] if total_row else 0

            # Count stocks with missing critical data (no score or no price)
            incomplete_row = conn.execute(
                """SELECT COUNT(DISTINCT symbol) as cnt FROM fundamentals_pit
                   WHERE as_of_date = ?
                     AND (score IS NULL OR score = 0 OR price IS NULL OR price = 0)""",
                (latest_date,),
            ).fetchone()
            incomplete = incomplete_row["cnt"] if incomplete_row else 0

            # All stocks in latest snapshot share the same as_of_date
            # So freshness is uniform — classify by the snapshot age
            if latest_age <= FRESH_MAX_DAYS:
                fresh = total - incomplete
                stale = 0
                expired = 0
            elif latest_age <= STALE_MAX_DAYS:
                fresh = 0
                stale = total - incomplete
                expired = 0
            else:
                fresh = 0
                stale = 0
                expired = total - incomplete

            stale_pct = ((stale + expired + incomplete) / max(total, 1)) * 100
            alert_active = stale_pct > UNIVERSE_STALE_ALERT_PCT

            alert_msg = None
            if alert_active:
                alert_msg = (
                    f"ALERT: {stale_pct:.0f}% of universe ({stale + expired + incomplete}/{total}) "
                    f"has stale or incomplete fundamentals. Data is {latest_age} days old."
                )

            return UniverseQuality(
                total_stocks=total,
                fresh_count=fresh,
                stale_count=stale,
                expired_count=expired,
                incomplete_count=incomplete,
                stale_pct=round(stale_pct, 1),
                alert_active=alert_active,
                alert_message=alert_msg,
            )
    except Exception:
        return UniverseQuality(0, 0, 0, 0, 0, 0.0, False, None)
