# db/__init__.py
"""
Sovereign AI Trading Engine — Database Abstraction Layer (v4.0)
Provides both sync and async session factories for PostgreSQL/TimescaleDB.
Falls back to SQLite for local development.

Public API re-exported from db.repository for backwards compatibility.
"""

from db.repository import (  # noqa: F401
    # Constants
    DB_BUSY_TIMEOUT_MS,
    PIT_RETENTION_DAYS,
    SQLITE_WRITE_RETRIES,
    get_connection,
    get_fundamentals_snapshot_as_of,
    init_db,
    load_fundamentals_universe_as_of,
    prune_fundamentals_pit_retention,
    save_microcaps,
    save_multibaggers,
)
