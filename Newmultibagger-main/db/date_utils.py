"""Shared date normalization helpers for DB write and migration boundaries."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd

DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%Y/%m/%d", "%Y%m%d")


def normalize_date(value=None, *, default: str | None = None) -> str | None:
    """Normalize date-like values to ISO YYYY-MM-DD."""
    if value is None:
        return default
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return default
        return value.date().isoformat()

    text = str(value).strip()
    if not text:
        return default

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass

    for fmt in DATE_FORMATS:
        try:
            source = text[:11] if fmt == "%d-%b-%Y" else text[:10]
            return datetime.strptime(source, fmt).date().isoformat()
        except ValueError:
            continue

    parsed = pd.to_datetime(text, errors="coerce")
    if not pd.isna(parsed):
        return parsed.date().isoformat()

    return default


def normalize_as_of_date(value=None) -> str:
    """Normalize an as-of date, defaulting missing or invalid values to today."""
    return normalize_date(value, default=datetime.now().date().isoformat()) or datetime.now().date().isoformat()


def strict_normalize_date(value) -> str:
    """Normalize a date value to ISO YYYY-MM-DD or raise ValueError.

    Unlike normalize_date, this never silently defaults. Use at write
    boundaries to reject garbage dates before they reach the DB.
    """
    if value is None:
        raise ValueError("as_of_date must not be None")
    result = normalize_date(value, default=None)
    if result is None:
        raise ValueError(f"Cannot parse as_of_date: {value!r}")
    return result
