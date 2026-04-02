# db/__init__.py
"""
Sovereign AI Trading Engine — Database Abstraction Layer (v4.0)
Provides both sync and async session factories for PostgreSQL/TimescaleDB.
Falls back to SQLite for local development.

Public API re-exported from db.repository for backwards compatibility.
"""
from db.repository import (  # noqa: F401
    get_connection,
    init_db,
    save_multibaggers,
    save_microcaps,
    prune_fundamentals_pit_retention,
    get_fundamentals_snapshot_as_of,
    load_fundamentals_universe_as_of,
    # Constants
    DB_BUSY_TIMEOUT_MS,
    SQLITE_WRITE_RETRIES,
    PIT_RETENTION_DAYS,
)
