import os
import threading
from contextlib import contextmanager
from pathlib import Path

import structlog
from sqlalchemy import text

from db.engine import DATABASE_URL, DEFAULT_SQLITE_PATH, engine as db_engine

logger = structlog.get_logger("db_core")

# Database Configuration
# CRITICAL: The canonical data lives in runtime/stocks.db, NOT the root stocks.db
DB_NAME = "stocks.db"
_ENGINE_SQLITE_PATH = db_engine.url.database if db_engine.dialect.name == "sqlite" else None
DB_PATH = os.path.abspath(str(_ENGINE_SQLITE_PATH or DEFAULT_SQLITE_PATH))


def get_engine():
    """Return the canonical SQLAlchemy Engine from db.engine."""
    if DATABASE_URL.startswith("sqlite"):
        Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return db_engine


@contextmanager
def get_db_connection():
    """
    Context manager that yields a SQLAlchemy connection.
    This replaces the legacy raw sqlite3 connection generation.
    Usage:
        with get_db_connection() as conn:
            conn.execute(text("SELECT ..."))
    """
    conn = db_engine.connect()
    try:
        # Apply SQLite WAL and busy timeout at connection level if using SQLite
        if db_engine.dialect.name == "sqlite":
            conn.execute(text("PRAGMA busy_timeout=5000"))
            conn.execute(text("PRAGMA journal_mode=WAL"))
        yield conn
    finally:
        conn.close()


def execute_sql(query: str, params: dict | None = None, fetch_all: bool = False):
    """
    Helper function to execute parameterized SQL dynamically supporting both PostgreSQL and SQLite.
    Always uses SQLAlchemy named parameters (e.g., :param_name).
    """
    params = params or {}
    with get_db_connection() as conn:
        result = conn.execute(text(query), params)
        if fetch_all:
            # Convert SQLAlchemy rows to list of dictionaries
            return [dict(row._mapping) for row in result]
        conn.commit()
        return result.rowcount


# -- DuckDB Analytical Engine (Thread-Safe) --
import duckdb

# Thread-local storage ensures each thread gets its own DuckDB connection
_duck_local = threading.local()


def get_duckdb_connection():
    """
    Returns a thread-local DuckDB connection configured to read from the local SQLite database.
    Each thread gets its own connection to avoid thread-safety issues.
    """
    conn = getattr(_duck_local, "conn", None)
    if conn is not None:
        try:
            # Verify connection is still alive
            conn.execute("SELECT 1").fetchone()
            return conn
        except Exception:
            conn = None

    # Create a fresh in-memory connection for this thread
    conn = duckdb.connect(":memory:")

    # Load SQLite scanner extension and attach the primary database.
    # Graceful degradation: if the extension cannot be installed (e.g. no
    # network access in CI/sandboxed environments), DuckDB continues in
    # pure in-memory mode and all queries fall back to the SQLite path.
    _duck_attached = False
    # Skip extension install in test/sandbox environments
    if __import__("os").getenv("DUCKDB_SKIP_SQLITE_EXT", "").lower() in ("1", "true", "yes"):
        _duck_local.conn = conn
        return conn

    try:
        try:
            conn.execute("LOAD sqlite;")
        except Exception:
            try:
                conn.execute("INSTALL sqlite;")
                conn.execute("LOAD sqlite;")
            except Exception as install_err:
                logger.warning(
                    "DuckDB sqlite_scanner unavailable — falling back to SQLite-only mode",
                    error=str(install_err),
                )
                _duck_local.conn = conn
                return conn   # return early — callers will use execute_sql() SQLite path

        # Handle SQLite type mismatches (e.g. score column declared INT but contains floats)
        conn.execute("SET sqlite_all_varchar=true;")
        # Attach the existing SQLite database in read-only mode for analytical queries
        db_path_fwd = DB_PATH.replace("\\", "/")
        conn.execute(f"ATTACH '{db_path_fwd}' AS sqlite_db (TYPE SQLITE, READ_ONLY);")
        _duck_attached = True
        logger.info("DuckDB analytical engine attached", db_path=DB_PATH)
    except Exception as e:
        logger.error("Failed to attach SQLite to DuckDB", error=str(e), db_path=DB_PATH)

    _duck_local.conn = conn
    return conn


# Lazy property — callers import `duck_conn` but it resolves per-thread
class _DuckConnProxy:
    """Thread-safe proxy that returns per-thread DuckDB connections."""

    def execute(self, *args, **kwargs):
        return get_duckdb_connection().execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(get_duckdb_connection(), name)


duck_conn = _DuckConnProxy()
