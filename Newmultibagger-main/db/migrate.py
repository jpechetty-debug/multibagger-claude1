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
from core.observability.logger import get_logger
_log = get_logger("db.migrate")

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
        _log.warning(f"  ⚠ Table '{table_name}' not found in SQLite source. Skipping.")
        return pd.DataFrame()


def run_migration():
    """Execute the full SQLite → PostgreSQL migration."""
    if IS_SQLITE:
        _log.warning("⚠ DATABASE_URL points to SQLite. Migration requires a PostgreSQL target.")
        _log.info("  Set DATABASE_URL=postgresql+psycopg://user:pass@host:5432/sovereign_db")
        return

    if not os.path.exists(SQLITE_SOURCE):
        _log.warning(f"⚠ SQLite source '{SQLITE_SOURCE}' not found. Nothing to migrate.")
        return

    _log.info(f"🔄 Starting migration: {SQLITE_SOURCE} → PostgreSQL")
    _log.info(f"   Target: {engine.url}")

    # Step 1: Create all tables in PostgreSQL
    _log.info("\n📐 Creating PostgreSQL schema...")
    init_tables()

    # Step 2: Connect to SQLite source
    sqlite_conn = sqlite3.connect(SQLITE_SOURCE)

    # Step 3: Migrate each table
    total_rows = 0
    for table_name in MIGRATION_ORDER:
        _log.info(f"\n📦 Migrating: {table_name}")
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
            _log.info(f"  ✅ {row_count:,} rows migrated successfully.")
        except Exception as e:
            _log.error(f"  ❌ Migration failed for {table_name}: {e}")

    sqlite_conn.close()

    _log.info(f"\n{'=' * 50}")
    _log.info(f"✅ Migration Complete: {total_rows:,} total rows transferred.")
    _log.info(f"   Source: {SQLITE_SOURCE}")
    _log.info("   Target: PostgreSQL/TimescaleDB")
    _log.info(f"{'=' * 50}")


if __name__ == "__main__":
    run_migration()
