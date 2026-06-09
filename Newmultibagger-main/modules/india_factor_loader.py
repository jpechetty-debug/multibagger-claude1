"""
India Factor Returns Loader
---------------------------
Loads weekly India equity factor returns from ``data/india_factor_returns.csv``.

Columns in the CSV
~~~~~~~~~~~~~~~~~~
date            YYYY-MM-DD, weekly (Monday)
nifty_market    Broad Nifty 500 excess return over risk-free
size            Small-cap minus large-cap (SMB analog)
value           High B/P minus low B/P (HML analog)
momentum        12-1 month price momentum
quality         High ROE / low leverage minus opposite
low_vol         Low-beta minus high-beta (BAB analog)

All returns are expressed as weekly decimals (e.g. 0.012 = 1.2 %).

Public interface
~~~~~~~~~~~~~~~~
load_factor_returns(start, end) -> dict[str, pd.Series]
    Returns a dict of ``{factor_name: weekly_return_series}`` aligned on a
    DatetimeIndex.  Pass ``start`` / ``end`` as ISO strings or ``date`` objects
    to restrict the window.  Passing ``None`` returns the full history.
"""
from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from core.observability.logger import get_logger

_log = get_logger("modules.india_factor_loader")

# Resolve path relative to this file so it works regardless of cwd.
_HERE = Path(__file__).resolve().parent
_CSV_PATH_ENV = os.getenv("INDIA_FACTOR_CSV")
_DEFAULT_CSV = _HERE.parent / "data" / "india_factor_returns.csv"
FACTOR_CSV_PATH = Path(_CSV_PATH_ENV) if _CSV_PATH_ENV else _DEFAULT_CSV

FACTOR_COLUMNS = ["nifty_market", "size", "value", "momentum", "quality", "low_vol"]


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_raw() -> pd.DataFrame:
    """Parse CSV once and cache.  Returns a DatetimeIndex DataFrame."""
    if not FACTOR_CSV_PATH.exists():
        _log.warning(
            "india_factor_returns.csv not found",
            path=str(FACTOR_CSV_PATH),
            hint="Place the CSV at data/india_factor_returns.csv or set INDIA_FACTOR_CSV env var",
        )
        return pd.DataFrame(columns=["date"] + FACTOR_COLUMNS)

    df = pd.read_csv(FACTOR_CSV_PATH, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df = df.set_index("date")
    df.index = pd.DatetimeIndex(df.index)

    missing = [c for c in FACTOR_COLUMNS if c not in df.columns]
    if missing:
        _log.warning("Missing factor columns in CSV", missing=missing)

    _log.info(
        "India factor returns loaded",
        rows=len(df),
        start=str(df.index.min().date()) if len(df) else "n/a",
        end=str(df.index.max().date()) if len(df) else "n/a",
        factors=list(df.columns),
    )
    return df


def _to_date(val: Any) -> pd.Timestamp | None:
    if val is None:
        return None
    if isinstance(val, pd.Timestamp):
        return val
    if isinstance(val, (date, datetime)):
        return pd.Timestamp(val)
    return pd.Timestamp(str(val))


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def load_factor_returns(
    start: str | date | None = None,
    end: str | date | None = None,
    factors: list[str] | None = None,
) -> dict[str, pd.Series]:
    """Return India factor return series as a dict of ``{name: pd.Series}``.

    Args:
        start: Inclusive start date (ISO string, ``date``, or ``None`` for full history).
        end:   Inclusive end date (ISO string, ``date``, or ``None`` for full history).
        factors: Subset of factor names to return.  Defaults to all six columns.

    Returns:
        ``{factor_name: weekly_return_series}`` with a ``DatetimeIndex``.
        Empty dict if the CSV is missing or no rows match the window.
    """
    df = _load_raw()
    if df.empty:
        return {}

    t_start = _to_date(start)
    t_end = _to_date(end)

    if t_start is not None:
        df = df[df.index >= t_start]
    if t_end is not None:
        df = df[df.index <= t_end]

    if df.empty:
        _log.warning("No factor rows in requested window", start=str(start), end=str(end))
        return {}

    wanted = factors if factors else FACTOR_COLUMNS
    result: dict[str, pd.Series] = {}
    for col in wanted:
        if col in df.columns:
            result[col] = df[col].astype(float)
        else:
            _log.warning("Requested factor not in CSV", factor=col)

    return result


def factor_metadata() -> dict[str, Any]:
    """Return availability metadata — useful for health-check / debug endpoints."""
    df = _load_raw()
    if df.empty:
        return {"available": False, "rows": 0, "factors": []}
    return {
        "available": True,
        "rows": len(df),
        "start": str(df.index.min().date()),
        "end": str(df.index.max().date()),
        "factors": [c for c in FACTOR_COLUMNS if c in df.columns],
    }
