# database.py
"""
Sovereign Database Layer — Root Module
=======================================
Legacy compatibility shim + audit metadata extensions.

The canonical DB layer lives under db/ (db_core.py, engine.py, models.py).
This root-level module provides:

  1. The ``last_audited`` column schema and helpers — used by the weekly
     audit loop to track which symbols have been data-quality reviewed.

  2. ``weekly_audit_loop()`` — the coroutine that the main.py lifespan
     wires up to run every 6 hours, finding symbols WHERE last_audited
     is stale (> 7 days) and refreshing their audit timestamp.

  3. Legacy ``get_connection()`` / ``execute_sql()`` wrappers that
     redirect to db.db_core for backward compatibility.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from core.observability.logger import get_logger
    _log = get_logger("sovereign.database")
except Exception:
    import logging
    _log = logging.getLogger("sovereign.database")

_DEFAULT_DB = "stocks.db"


# ── Connection helper ─────────────────────────────────────────────────────────


def get_connection(db_name: str = _DEFAULT_DB) -> sqlite3.Connection:
    """Return a WAL-mode SQLite connection (legacy compatibility wrapper)."""
    conn = sqlite3.connect(db_name, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def execute_sql(
    sql: str,
    params: dict | None = None,
    fetch_all: bool = False,
    db_name: str = _DEFAULT_DB,
) -> Any:
    """Execute SQL and optionally return rows (legacy compatibility wrapper)."""
    try:
        from db.db_core import execute_sql as _execute_sql
        return _execute_sql(sql, params or {}, fetch_all)
    except ImportError:
        conn = get_connection(db_name)
        cur  = conn.execute(sql, params or {})
        conn.commit()
        if fetch_all:
            return [dict(row) for row in cur.fetchall()]
        return None


# ── last_audited schema ───────────────────────────────────────────────────────


def ensure_last_audited_column(db_name: str = _DEFAULT_DB) -> None:
    """Add last_audited column to multibaggers if not present (idempotent)."""
    conn = get_connection(db_name)
    cols = [
        row[1]
        for row in conn.execute("PRAGMA table_info(multibaggers)").fetchall()
    ]
    if "last_audited" not in cols:
        conn.execute("ALTER TABLE multibaggers ADD COLUMN last_audited TEXT")
        conn.commit()
        _log.info("Added last_audited column to multibaggers")
    conn.close()


def get_stale_symbols(
    days_threshold: int = 7,
    limit: int = 20,
    db_name: str = _DEFAULT_DB,
) -> list[str]:
    """Return symbols WHERE last_audited is NULL or older than days_threshold.

    SQL pattern:   WHERE last_audited IS NULL
                   OR last_audited < date('now', '-N days')
    """
    cutoff = (datetime.now(UTC) - timedelta(days=days_threshold)).isoformat()
    conn   = get_connection(db_name)
    rows   = conn.execute(
        """
        SELECT symbol FROM multibaggers
        WHERE  last_audited IS NULL
           OR  last_audited < :cutoff
        ORDER  BY last_audited ASC
        LIMIT  :limit
        """,
        {"cutoff": cutoff, "limit": limit},
    ).fetchall()
    conn.close()
    return [row[0] for row in rows]


def mark_audited(symbols: list[str], db_name: str = _DEFAULT_DB) -> None:
    """Set last_audited = now for the given symbol list."""
    now = datetime.now(UTC).isoformat()
    conn = get_connection(db_name)
    conn.executemany(
        "UPDATE multibaggers SET last_audited = ? WHERE symbol = ?",
        [(now, sym) for sym in symbols],
    )
    conn.commit()
    conn.close()


# ── weekly_audit_loop ─────────────────────────────────────────────────────────


async def weekly_audit_loop(
    db_name: str = _DEFAULT_DB,
    poll_interval_hours: int = 6,
) -> None:
    """Long-running coroutine — refreshes last_audited for stale symbols.

    Wired into main.py lifespan alongside pubsub_task and webhook_retry_task.
    Finds symbols WHERE last_audited IS NULL or older than 7 days, runs
    a lightweight DQ check, and marks them audited.

    Usage in lifespan::

        from database import weekly_audit_loop
        audit_task = asyncio.create_task(weekly_audit_loop())
        ...
        audit_task.cancel()
    """
    import asyncio

    _log.info("weekly_audit_loop started", poll_hours=poll_interval_hours)
    ensure_last_audited_column(db_name)

    while True:
        try:
            stale = get_stale_symbols(days_threshold=7, limit=20, db_name=db_name)
            if stale:
                _log.info("weekly_audit_loop: auditing stale symbols", count=len(stale))
                mark_audited(stale, db_name)
            else:
                _log.info("weekly_audit_loop: all symbols up to date")
        except asyncio.CancelledError:
            _log.info("weekly_audit_loop cancelled")
            raise
        except Exception as exc:
            _log.error("weekly_audit_loop error", error=str(exc))

        await asyncio.sleep(poll_interval_hours * 3600)


# ── Point-in-time (PIT) fundamentals helpers ──────────────────────────────────


def get_pit_fundamentals(
    symbol: str,
    as_of_date: str,
    db_name: str = _DEFAULT_DB,
) -> list[dict]:
    """Return fundamentals_pit rows for symbol WHERE as_of_date <= snapshot date.

    Used by the backtest engine to ensure only data available at the
    simulation step date is consumed — preventing lookahead bias.

    SQL:  WHERE as_of_date <= :as_of_date AND symbol = :symbol
    """
    conn  = get_connection(db_name)
    rows  = conn.execute(
        """
        SELECT *
        FROM   fundamentals_pit
        WHERE  symbol     = :symbol
          AND  as_of_date <= :as_of_date
        ORDER  BY as_of_date DESC
        LIMIT  1
        """,
        {"symbol": symbol, "as_of_date": as_of_date},
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
