# modules/errors.py
"""
Sovereign AI — Structured Error Responses

Replaces ad-hoc {"error": str(e)} patterns with typed error models.
Used across all API routes for consistent error shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SovereignError(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] | None = None
    timestamp: str = ""

    def __init__(self, **data):
        if not data.get("timestamp"):
            data["timestamp"] = datetime.now().isoformat()
        super().__init__(**data)


class SovereignErrorExc(Exception):
    """Raisable exception that carries structured SovereignError fields.

    Use this in scoring gates where you need ``raise stale_data_error(...)``.
    Catch with ``except SovereignErrorExc`` and inspect ``.error_code`` / ``.details``.
    """

    def __init__(self, error_code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details or {}


def provider_error(provider: str, symbol: str, exc: Exception | str) -> SovereignError:
    return SovereignError(
        error_code="PROVIDER_FAILURE",
        message=f"Data provider '{provider}' failed for {symbol}",
        details={"provider": provider, "symbol": symbol, "error": str(exc)},
    )


def data_error(message: str, **details: Any) -> SovereignError:
    return SovereignError(
        error_code="DATA_ERROR",
        message=message,
        details=details or None,
    )


def stale_data_error(symbol: str, age_days: int) -> SovereignErrorExc:
    """Return a raisable exception for stale fundamental data."""
    return SovereignErrorExc(
        error_code="STALE_DATA",
        message=f"Data for {symbol} is {age_days} days old — exceeds freshness threshold",
        details={"symbol": symbol, "age_days": age_days},
    )


def validation_error(message: str, field: str | None = None) -> SovereignError:
    return SovereignError(
        error_code="VALIDATION_ERROR",
        message=message,
        details={"field": field} if field else None,
    )


def not_found_error(resource: str, identifier: str) -> SovereignError:
    return SovereignError(
        error_code="NOT_FOUND",
        message=f"{resource} '{identifier}' not found",
        details={"resource": resource, "identifier": identifier},
    )


def internal_error(operation: str, exc: Exception | str) -> SovereignError:
    return SovereignError(
        error_code="INTERNAL_ERROR",
        message=f"Unexpected error during {operation}",
        details={"operation": operation, "error": str(exc)},
    )
