# modules/connections.py
import asyncio
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from db.db_core import db_engine
from modules.runtime_settings import runtime_settings
from modules.structured_logger import SovereignLogger

runtime_logger = SovereignLogger("sovereign.runtime")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
DB_NAME = "stocks.db"
DB_PATH = str(RUNTIME_DIR / DB_NAME)

DB_BUSY_TIMEOUT_MS = runtime_settings.sqlite_busy_timeout_ms
SQLITE_WRITE_RETRIES = runtime_settings.sqlite_write_retries
SQLITE_RETRY_BASE_SECONDS = runtime_settings.sqlite_retry_base_seconds
BLOCKING_IO_CONCURRENCY = runtime_settings.blocking_io_concurrency

blocking_io_semaphore = asyncio.Semaphore(BLOCKING_IO_CONCURRENCY)
ticker_io_semaphore = asyncio.Semaphore(runtime_settings.ticker_io_concurrency)


def _is_sqlite_lock_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "database is locked" in msg or "database table is locked" in msg


async def _run_blocking(fn: Callable[..., Any], *args, **kwargs):
    async with blocking_io_semaphore:
        return await asyncio.to_thread(fn, *args, **kwargs)


async def _run_ticker_blocking(fn: Callable[..., Any], *args, **kwargs):
    async with ticker_io_semaphore, blocking_io_semaphore:
        return await asyncio.to_thread(fn, *args, **kwargs)


async def _run_sqlite_write_with_retry(write_fn: Callable[[], Any], operation_name: str):
    for attempt in range(SQLITE_WRITE_RETRIES):
        try:
            return await _run_blocking(write_fn)
        except sqlite3.OperationalError as exc:
            if _is_sqlite_lock_error(exc) and attempt < SQLITE_WRITE_RETRIES - 1:
                wait = SQLITE_RETRY_BASE_SECONDS * (2**attempt)
                runtime_logger.warning(
                    "SQLite lock during async write; retrying",
                    operation=operation_name,
                    wait_seconds=round(wait, 2),
                    attempt=attempt + 1,
                )
                await asyncio.sleep(wait)
                continue
            raise


def _run_sqlite_write_with_retry_sync(write_fn: Callable[[], Any], operation_name: str):
    for attempt in range(SQLITE_WRITE_RETRIES):
        try:
            return write_fn()
        except sqlite3.OperationalError as exc:
            if _is_sqlite_lock_error(exc) and attempt < SQLITE_WRITE_RETRIES - 1:
                wait = SQLITE_RETRY_BASE_SECONDS * (2**attempt)
                runtime_logger.warning(
                    "SQLite lock during sync write; retrying",
                    operation=operation_name,
                    wait_seconds=round(wait, 2),
                    attempt=attempt + 1,
                )
                time.sleep(wait)
                continue
            raise


def get_connection():
    """Returns a connection from the centralized SQLAlchemy pool."""

    return db_engine.raw_connection()
