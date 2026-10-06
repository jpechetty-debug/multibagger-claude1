"""
Daily adjusted closes for every symbol that has PIT feature snapshots.

ML training labels each snapshot with its forward return. Those prices must come
from a full price history, not from later snapshots: later snapshots only hold
stocks that are still picks, so labelling from them would only ever see survivors.

Stored in pit_store.db table ``price_history``. Updated incrementally:
    python -m modules.data_layer.price_history
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

from core.observability.logger import get_logger
from modules.data_layer.db_utils import get_db_connection

_log = get_logger("modules.data_layer.price_history")

CHUNK = 100
_DDL = "CREATE TABLE IF NOT EXISTS price_history (symbol TEXT, date TEXT, close REAL, PRIMARY KEY (symbol, date))"


def _ensure(conn: sqlite3.Connection) -> None:
    conn.execute(_DDL)


def store_closes(closes: pd.DataFrame) -> int:
    """Upsert a wide frame of closes (index = dates, columns = symbols). Returns rows written."""
    long = closes.stack().dropna().reset_index()
    long.columns = ["date", "symbol", "close"]
    long = long[long["close"] > 0]
    if long.empty:
        return 0
    long["date"] = pd.to_datetime(long["date"]).dt.strftime("%Y-%m-%d")
    with get_db_connection("pit_store.db") as conn:
        _ensure(conn)
        conn.executemany(
            "INSERT OR REPLACE INTO price_history (symbol, date, close) VALUES (?, ?, ?)",
            long[["symbol", "date", "close"]].itertuples(index=False, name=None),
        )
        conn.commit()
    return len(long)


def load_closes() -> pd.DataFrame:
    """Long frame: symbol, date (datetime), close."""
    with get_db_connection("pit_store.db") as conn:
        _ensure(conn)
        df = pd.read_sql("SELECT symbol, date, close FROM price_history", conn)
    df["date"] = pd.to_datetime(df["date"])
    return df


def _universe() -> tuple[list[str], date | None]:
    with get_db_connection("stocks.db") as conn:
        rows = conn.execute("SELECT DISTINCT symbol FROM fundamentals_pit").fetchall()
        first = conn.execute("SELECT MIN(as_of_date) FROM fundamentals_pit").fetchone()[0]
    return sorted(r[0] for r in rows if r[0]), (date.fromisoformat(first[:10]) if first else None)


def update_price_history(symbols: list[str] | None = None, start: date | None = None) -> int:
    """Download closes from ``start`` (default: day after the latest stored, or first PIT date)."""
    import yfinance as yf

    universe, first_pit = _universe()
    symbols = symbols or universe
    if start is None:
        with get_db_connection("pit_store.db") as conn:
            _ensure(conn)
            latest = conn.execute("SELECT MAX(date) FROM price_history").fetchone()[0]
        start = date.fromisoformat(latest) + timedelta(days=1) if latest else first_pit
    if not symbols or start is None or start > date.today():
        return 0

    written = 0
    for i in range(0, len(symbols), CHUNK):
        batch = symbols[i : i + CHUNK]
        try:
            data = yf.download(batch, start=start.isoformat(), auto_adjust=True, progress=False, threads=True)
        except Exception as exc:  # one bad chunk must not stop the rest
            _log.warning("Price download failed", chunk=i, error=str(exc))
            continue
        if data is None or data.empty:
            continue
        closes = data["Close"]
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(batch[0])
        written += store_closes(closes)
    _log.info("Price history updated", symbols=len(symbols), start=str(start), rows=written)
    return written


if __name__ == "__main__":
    print(f"rows written: {update_price_history()}")
