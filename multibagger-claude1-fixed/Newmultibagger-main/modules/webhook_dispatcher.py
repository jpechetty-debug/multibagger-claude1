"""
Sovereign Webhook Dispatcher
============================

Responsibilities
----------------
1. **Sign** — every outbound payload gets an ``X-Sovereign-Signature``
   header (``sha256=<hmac_hex>``) so subscribers can verify authenticity.

2. **Dispatch** — fire-and-forget ``httpx.AsyncClient.post()`` with a
   5-second timeout.  The result (success or failure) is written to
   ``alert_dispatch_log``.

3. **Retry** — a background coroutine polls ``alert_dispatch_log`` for
   rows with ``status='failed'`` and ``next_retry_at <= now``, and
   re-dispatches them with exponential back-off (1 min → 2 → 4 → … → 2 h
   cap, up to ``max_failures`` consecutive failures per subscription).

4. **Auto-disable** — after ``max_failures`` consecutive failures the
   subscription is set ``is_active=0`` so the polling loop stops hammering
   a dead endpoint.

Signature verification (subscriber side, Python example)::

    import hashlib, hmac
    secret = b"<your-secret-hex>"
    body   = request.body()          # raw bytes
    sig    = request.headers["X-Sovereign-Signature"]   # "sha256=<hex>"
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig, expected)

Usage (caller side)::

    from modules.webhook_dispatcher import dispatch_alerts, start_retry_worker

    # In lifespan:
    retry_task = asyncio.create_task(start_retry_worker())

    # After AlertEngine.check_portfolio():
    await dispatch_alerts(alert_list)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from db.db_core import execute_sql
from core.observability.logger import get_logger

_log = get_logger("sovereign.webhooks")

# ── Tuning constants ──────────────────────────────────────────────────────────

_DISPATCH_TIMEOUT_SECONDS = 5.0
_RETRY_POLL_INTERVAL_SECONDS = 60          # how often the retry worker wakes
_RETRY_BASE_DELAY_MINUTES = 1
_RETRY_MAX_DELAY_MINUTES = 120             # 2-hour cap

# ── Signature ─────────────────────────────────────────────────────────────────


def _sign_payload(secret_hex: str, body: bytes) -> str:
    """Return ``sha256=<hmac_hex>`` for the given body and subscriber secret."""
    sig = hmac.new(secret_hex.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


# ── DB helpers ────────────────────────────────────────────────────────────────


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _active_subscriptions(event_type: str) -> list[dict]:
    """Return all active subscriptions that want this event_type."""
    rows = execute_sql(
        """
        SELECT id, url, secret, event_filter, max_failures, consecutive_failures
        FROM   webhook_subscriptions
        WHERE  is_active = 1
        """,
        fetch_all=True,
    )
    matched = []
    for row in (rows or []):
        ef = row.get("event_filter")
        if ef is None:
            matched.append(row)
        else:
            allowed = {t.strip().upper() for t in ef.split(",")}
            if event_type.upper() in allowed:
                matched.append(row)
    return matched


def _log_dispatch(
    *,
    subscription_id: int,
    payload_json: str,
    http_status: int | None,
    status: str,
    error_detail: str | None,
    next_retry_at: datetime | None,
    attempt_count: int,
) -> None:
    execute_sql(
        """
        INSERT INTO alert_dispatch_log
            (subscription_id, payload, http_status, status,
             error_detail, attempt_count, next_retry_at, dispatched_at)
        VALUES
            (:sid, :payload, :http_status, :status,
             :error, :attempt_count, :next_retry_at, :dispatched_at)
        """,
        {
            "sid": subscription_id,
            "payload": payload_json,
            "http_status": http_status,
            "status": status,
            "error": error_detail,
            "attempt_count": attempt_count,
            "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
            "dispatched_at": _now_utc().isoformat(),
        },
    )


def _update_log_row(
    *,
    log_id: int,
    http_status: int | None,
    status: str,
    error_detail: str | None,
    next_retry_at: datetime | None,
    attempt_count: int,
) -> None:
    execute_sql(
        """
        UPDATE alert_dispatch_log
        SET    http_status   = :http_status,
               status        = :status,
               error_detail  = :error,
               next_retry_at = :next_retry_at,
               attempt_count = :attempt_count
        WHERE  id = :id
        """,
        {
            "id": log_id,
            "http_status": http_status,
            "status": status,
            "error": error_detail,
            "next_retry_at": next_retry_at.isoformat() if next_retry_at else None,
            "attempt_count": attempt_count,
        },
    )


def _increment_failures(subscription_id: int, max_failures: int) -> None:
    """Increment consecutive_failures; auto-disable when cap reached."""
    execute_sql(
        """
        UPDATE webhook_subscriptions
        SET    consecutive_failures = consecutive_failures + 1,
               is_active = CASE
                   WHEN consecutive_failures + 1 >= :max_failures THEN 0
                   ELSE is_active
               END,
               updated_at = :now
        WHERE  id = :id
        """,
        {"id": subscription_id, "max_failures": max_failures, "now": _now_utc().isoformat()},
    )


def _reset_failures(subscription_id: int) -> None:
    execute_sql(
        """
        UPDATE webhook_subscriptions
        SET consecutive_failures = 0, updated_at = :now
        WHERE id = :id
        """,
        {"id": subscription_id, "now": _now_utc().isoformat()},
    )


def _retry_delay(attempt: int) -> datetime:
    """Exponential back-off: 1 min → 2 → 4 → … capped at 2 hours."""
    minutes = min(_RETRY_BASE_DELAY_MINUTES * (2 ** attempt), _RETRY_MAX_DELAY_MINUTES)
    return _now_utc() + timedelta(minutes=minutes)


# ── Core dispatch ─────────────────────────────────────────────────────────────


async def _post_one(
    *,
    client: httpx.AsyncClient,
    subscription: dict,
    payload_json: str,
    attempt_count: int,
    log_id: int | None = None,
) -> bool:
    """POST payload to one subscriber.  Returns True on success (2xx)."""
    sub_id: int = subscription["id"]
    url: str = subscription["url"]
    secret: str = subscription["secret"]
    max_failures: int = subscription.get("max_failures", 5)

    body = payload_json.encode()
    sig = _sign_payload(secret, body)

    http_status: int | None = None
    error_detail: str | None = None
    success = False

    try:
        resp = await client.post(
            url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Sovereign-Signature": sig,
                "User-Agent": "Sovereign-Webhook/1.0",
            },
            timeout=_DISPATCH_TIMEOUT_SECONDS,
        )
        http_status = resp.status_code
        success = 200 <= http_status < 300
        if not success:
            error_detail = f"HTTP {http_status}: {resp.text[:200]}"
    except httpx.TimeoutException:
        error_detail = "Timeout after 5 s"
    except Exception as exc:
        error_detail = str(exc)[:300]

    next_retry_at: datetime | None = None
    if success:
        status_str = "delivered"
        _reset_failures(sub_id)
    else:
        status_str = "failed"
        next_retry_at = _retry_delay(attempt_count)
        _increment_failures(sub_id, max_failures)
        _log.warning(
            "Webhook dispatch failed",
            subscription_id=sub_id,
            url=url,
            http_status=http_status,
            error=error_detail,
            next_retry_at=next_retry_at.isoformat(),
        )

    if log_id is None:
        _log_dispatch(
            subscription_id=sub_id,
            payload_json=payload_json,
            http_status=http_status,
            status=status_str,
            error_detail=error_detail,
            next_retry_at=next_retry_at,
            attempt_count=attempt_count,
        )
    else:
        _update_log_row(
            log_id=log_id,
            http_status=http_status,
            status=status_str,
            error_detail=error_detail,
            next_retry_at=next_retry_at,
            attempt_count=attempt_count,
        )

    return success


# ── Public API ────────────────────────────────────────────────────────────────


async def dispatch_alerts(alerts: list[dict[str, Any]]) -> None:
    """Fan-out a list of alert dicts to all matching active subscribers.

    Called by the AlertEngine integration after check_portfolio() returns.
    Each alert is dispatched independently so one failing subscriber cannot
    block others.
    """
    if not alerts:
        return

    async with httpx.AsyncClient() as client:
        tasks = []
        for alert in alerts:
            event_type: str = alert.get("type", "UNKNOWN")
            subscriptions = _active_subscriptions(event_type)
            if not subscriptions:
                continue

            payload = {
                "event": event_type,
                "alert": alert,
                "sent_at": _now_utc().isoformat(),
            }
            payload_json = json.dumps(payload, separators=(",", ":"))

            for sub in subscriptions:
                tasks.append(
                    _post_one(
                        client=client,
                        subscription=sub,
                        payload_json=payload_json,
                        attempt_count=0,
                    )
                )

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            delivered = sum(1 for r in results if r is True)
            _log.info(
                "Alert fan-out complete",
                total_alerts=len(alerts),
                total_dispatches=len(tasks),
                delivered=delivered,
                failed=len(tasks) - delivered,
            )


async def start_retry_worker() -> None:
    """Background coroutine — poll for failed dispatches and retry them.

    Wire into lifespan::

        retry_task = asyncio.create_task(start_retry_worker())
        ...
        retry_task.cancel()
    """
    _log.info("Webhook retry worker started", poll_interval_seconds=_RETRY_POLL_INTERVAL_SECONDS)

    while True:
        try:
            await _run_retry_pass()
        except asyncio.CancelledError:
            _log.info("Webhook retry worker cancelled")
            raise
        except Exception as exc:
            _log.error("Webhook retry worker error", error=str(exc))

        await asyncio.sleep(_RETRY_POLL_INTERVAL_SECONDS)


async def _run_retry_pass() -> None:
    """One sweep: find due failed rows, re-dispatch, update log."""
    now_iso = _now_utc().isoformat()
    pending = execute_sql(
        """
        SELECT  l.id            AS log_id,
                l.subscription_id,
                l.payload,
                l.attempt_count,
                s.url,
                s.secret,
                s.max_failures,
                s.consecutive_failures,
                s.is_active
        FROM    alert_dispatch_log l
        JOIN    webhook_subscriptions s ON s.id = l.subscription_id
        WHERE   l.status        = 'failed'
          AND   l.next_retry_at <= :now
          AND   s.is_active     = 1
        ORDER BY l.next_retry_at
        LIMIT  50
        """,
        {"now": now_iso},
        fetch_all=True,
    )

    if not pending:
        return

    _log.info("Retrying failed webhook dispatches", count=len(pending))
    async with httpx.AsyncClient() as client:
        tasks = []
        for row in pending:
            sub = {
                "id": row["subscription_id"],
                "url": row["url"],
                "secret": row["secret"],
                "max_failures": row["max_failures"],
                "consecutive_failures": row["consecutive_failures"],
            }
            tasks.append(
                _post_one(
                    client=client,
                    subscription=sub,
                    payload_json=row["payload"],
                    attempt_count=row["attempt_count"] + 1,
                    log_id=row["log_id"],
                )
            )
        await asyncio.gather(*tasks, return_exceptions=True)


# ── Secret generation helper (used by the registration endpoint) ───────────────


def generate_webhook_secret() -> str:
    """Return a 64-char hex secret (32 random bytes)."""
    return secrets.token_hex(32)
