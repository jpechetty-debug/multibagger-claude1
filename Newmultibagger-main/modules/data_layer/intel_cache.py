"""
Same-day cache for the live per-stock lookups made while scoring
(promoter / bulk-deal trend, analyst estimates).

Without it every score call hits NSE / yfinance: a full scan spends most of its
time on bulk-deal timeouts, and two scores of the same stock on the same day can
differ. Results are cached for the calendar day, failures included, so a timed-out
source is not retried for every stock rescored that day.

Set INTEL_CACHE_DISABLED=true to bypass it (always fetch live).
"""

from __future__ import annotations

import functools
import json
import os
import sqlite3
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

CACHE_PATH = Path(__file__).resolve().parents[2] / "runtime" / "intel_cache.db"
_FAILED = {"__intel_cache_failed__": True}


def _connect() -> sqlite3.Connection:
    CACHE_PATH.parent.mkdir(exist_ok=True)
    conn = sqlite3.connect(CACHE_PATH, timeout=30)
    conn.execute("CREATE TABLE IF NOT EXISTS intel (key TEXT PRIMARY KEY, day TEXT, value TEXT)")
    return conn


def daily_cached(namespace: str) -> Callable:
    """Cache ``fn(symbol)`` per symbol for the current day. Extra arguments bypass the cache."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def wrapper(symbol: str, *args: Any, **kwargs: Any) -> Any:
            if args or any(v is not None for v in kwargs.values()) or os.getenv("INTEL_CACHE_DISABLED", "").lower() == "true":
                return fn(symbol, *args, **kwargs)
            key, today = f"{namespace}:{symbol}", date.today().isoformat()
            with _connect() as conn:
                row = conn.execute("SELECT value FROM intel WHERE key = ? AND day = ?", (key, today)).fetchone()
            if row:
                value = json.loads(row[0])
                if value == _FAILED:
                    raise RuntimeError(f"{namespace} lookup for {symbol} already failed today (cached)")
                return value
            try:
                value = fn(symbol)
            except Exception:
                stored = _FAILED
                raise
            else:
                stored = value
            finally:
                try:
                    payload = json.dumps(stored, default=str)
                    with _connect() as conn:
                        conn.execute("INSERT OR REPLACE INTO intel VALUES (?, ?, ?)", (key, today, payload))
                except (TypeError, ValueError, sqlite3.Error):
                    pass  # an uncacheable result is still returned
            return value

        return wrapper

    return decorator
