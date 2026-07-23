"""
WebSocket connect-token helpers.

Flow
----
1. Frontend calls ``GET /api/ws-token`` (standard X-API-Key auth).
   Backend issues a short-lived HMAC-SHA256 token valid for
   WS_TOKEN_TTL_SECONDS (default 60 s).

2. Frontend opens ``ws://…/ws/prices?token=<token>``.
   The WebSocket endpoint calls ``verify_ws_token(token)`` before
   accepting the connection.  Expired or tampered tokens are rejected
   with close code 1008 (Policy Violation).

Why not JWT?
------------
We deliberately avoid a full JWT library dependency.  The token is a
simple ``{payload_b64}.{hmac_hex}`` structure — easy to audit and no
additional packages required (PyJWT is not in requirements.txt).

Secret management
-----------------
WS_TOKEN_SECRET must be a 256-bit (64-char hex) random value.
Generate with::

    python -c "import secrets; print(secrets.token_hex(32))"

Never commit the actual secret; keep it in .env only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import WebSocket

from core.observability.logger import get_logger

_log = get_logger("sovereign.ws_auth")

# ── Config ────────────────────────────────────────────────────────────────────

_SECRET_RAW = os.getenv("WS_TOKEN_SECRET", "")
_SECRET: bytes = _SECRET_RAW.encode() if _SECRET_RAW else b""

_TTL = int(os.getenv("WS_TOKEN_TTL_SECONDS", "60"))

# ── Internal helpers ──────────────────────────────────────────────────────────


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    # Restore stripped padding
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


def _sign(payload_b64: str) -> str:
    return hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────


def issue_ws_token(consumer: str = "browser") -> str:
    """Return a short-lived WS connect token.

    The token is ``{payload_b64}.{hmac_hex}`` where payload is a
    JSON object ``{"sub": consumer, "iat": unix_ts}``.

    Raises ``RuntimeError`` if ``WS_TOKEN_SECRET`` is not configured.
    """
    if not _SECRET:
        raise RuntimeError(
            "WS_TOKEN_SECRET is not set.  "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    payload: dict[str, Any] = {"sub": consumer, "iat": int(time.time())}
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    sig = _sign(payload_b64)
    return f"{payload_b64}.{sig}"


def verify_ws_token(token: str | None) -> bool:
    """Return True if the token is valid and not expired.

    Never raises — returns False for any invalid/expired input so the
    caller can close the WebSocket cleanly.
    """
    if not _SECRET:
        # Secret not configured → fail closed (deny connection).
        _log.error(
            "WS_TOKEN_SECRET is not configured; all WebSocket connections rejected. "
            "Set WS_TOKEN_SECRET in .env."
        )
        return False

    if not token or "." not in token:
        return False

    try:
        payload_b64, sig = token.rsplit(".", 1)
    except ValueError:
        return False

    # Constant-time comparison prevents timing attacks.
    expected = _sign(payload_b64)
    if not hmac.compare_digest(sig, expected):
        _log.warning("WS token HMAC mismatch — possible tampering")
        return False

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        return False

    issued_at = payload.get("iat", 0)
    age = time.time() - issued_at
    if age > _TTL or age < 0:
        _log.info("WS token expired", age_seconds=round(age, 1), ttl=_TTL)
        return False

    return True


async def ws_reject(websocket: WebSocket, code: int = 1008, reason: str = "Unauthorized") -> None:
    """Accept then immediately close a WebSocket with the given code.

    WebSocket close codes:
      1008 — Policy Violation (auth failure)
      1011 — Internal Error
    """
    try:
        await websocket.accept()
        await websocket.close(code=code, reason=reason)
    except Exception:
        pass
