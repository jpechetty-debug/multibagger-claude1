# db/migrate.py
"""
Sovereign AI Trading Engine v4.0 — SQLite → PostgreSQL Migration Script
One-time migration utility that reads all data from the existing SQLite
database and bulk-inserts it into the configured PostgreSQL/TimescaleDB instance.

Usage:
    1. Set DATABASE_URL to your PostgreSQL connection string.
    2. Run: python -m db.migrate
"""

import os
import sqlite3

import pandas as pd

from db.engine import IS_SQLITE, engine, init_tables
from modules.structured_logger import SovereignLogger, format_log_message
_log = SovereignLogger("db.migrate").logger

SQLITE_SOURCE = os.getenv("SQLITE_SOURCE", "stocks.db")

# Tables to migrate in dependency order
MIGRATION_ORDER = [
    "multibaggers",
    "fundamentals_pit",
    "score_history",
    "factor_penalties",
    "valuation_metrics",
    "microcaps",
    "executions",
    "slippage_metrics",
    "buy_thesis",
]


def _read_sqlite_table(sqlite_conn, table_name: str) -> pd.DataFrame:
    """Safely read a table from SQLite, returning empty DataFrame if missing."""
    try:
        return pd.read_sql(f"SELECT * FROM {table_name}", sqlite_conn)
    except Exception:
        _log.info(format_log_message(f"  ⚠ Table '{table_name}' not found in SQLite source. Skipping."))
        return pd.DataFrame()


def run_migration():
    """Execute the full SQLite → PostgreSQL migration."""
    if IS_SQLITE:
        _log.info(format_log_message("⚠ DATABASE_URL points to SQLite. Migration requires a PostgreSQL target."))
        _log.info(format_log_message("  Set DATABASE_URL=postgresql+psycopg://user:pass@host:5432/sovereign_db"))
        return

    if not os.path.exists(SQLITE_SOURCE):
        _log.info(format_log_message(f"⚠ SQLite source '{SQLITE_SOURCE}' not found. Nothing to migrate."))
        return

    _log.info(format_log_message(f"🔄 Starting migration: {SQLITE_SOURCE} → PostgreSQL"))
    _log.info(format_log_message(f"   Target: {engine.url}"))

    # Step 1: Create all tables in PostgreSQL
    _log.info(format_log_message("\n📐 Creating PostgreSQL schema..."))
    init_tables()

    # Step 2: Connect to SQLite source
    sqlite_conn = sqlite3.connect(SQLITE_SOURCE)

    # Step 3: Migrate each table
    total_rows = 0
    for table_name in MIGRATION_ORDER:
        _log.info(format_log_message(f"\n📦 Migrating: {table_name}"))
        df = _read_sqlite_table(sqlite_conn, table_name)

        if df.empty:
            continue

        row_count = len(df)
        try:
            df.to_sql(
                table_name,
                engine,
                if_exists="append",
                index=False,
                method="multi",
                chunksize=500,
            )
            total_rows += row_count
            _log.info(format_log_message(f"  ✅ {row_count:,} rows migrated successfully."))
        except Exception as e:
            _log.info(format_log_message(f"  ❌ Migration failed for {table_name}: {e}"))

    sqlite_conn.close()

    _log.info(format_log_message(f"\n{'=' * 50}"))
    _log.info(format_log_message(f"✅ Migration Complete: {total_rows:,} total rows transferred."))
    _log.info(format_log_message(f"   Source: {SQLITE_SOURCE}"))
    _log.info(format_log_message("   Target: PostgreSQL/TimescaleDB"))
    _log.info(format_log_message(f"{'=' * 50}"))


if __name__ == "__main__":
    run_migration()
