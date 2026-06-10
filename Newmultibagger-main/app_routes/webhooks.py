"""
Webhook Subscription Management
================================

Endpoints
---------
POST   /api/webhooks              Register a new endpoint
GET    /api/webhooks              List all subscriptions (secrets redacted)
DELETE /api/webhooks/{id}         Soft-delete (deactivate) a subscription
POST   /api/webhooks/{id}/test    Fire a synthetic test payload right now
GET    /api/webhooks/{id}/logs    Last 50 dispatch attempts for a subscription
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, Field, HttpUrl

from db.db_core import execute_sql
from modules.auth import get_api_key
from modules.webhook_dispatcher import dispatch_alerts, generate_webhook_secret
from core.observability.logger import get_logger

_log = get_logger("sovereign.webhooks_api")

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

_VALID_EVENT_TYPES = {"STOP_LOSS", "THESIS_BREAK", "PRICE_DRIFT", "REGIME_SHIFT", "DATA_STALE"}


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class WebhookCreate(BaseModel):
    name: str = Field(..., max_length=120, description="Human-readable label")
    url: HttpUrl = Field(..., description="HTTPS endpoint to POST alerts to")
    event_filter: list[str] | None = Field(
        default=None,
        description=(
            "Alert types to receive. Omit for all. "
            "Valid values: STOP_LOSS, THESIS_BREAK, PRICE_DRIFT, REGIME_SHIFT"
        ),
    )
    max_failures: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Auto-disable after this many consecutive delivery failures",
    )


class WebhookOut(BaseModel):
    id: int
    name: str
    url: str
    event_filter: str | None
    is_active: bool
    max_failures: int
    consecutive_failures: int
    created_at: str
    # secret is NEVER returned after the initial registration response


class WebhookCreated(WebhookOut):
    # Shown exactly once — the caller must store this.
    secret: str = Field(description="HMAC secret — store this now, it will not be shown again")


# ── Helpers ───────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _get_subscription_or_404(sub_id: int) -> dict:
    rows = execute_sql(
        "SELECT * FROM webhook_subscriptions WHERE id = :id",
        {"id": sub_id},
        fetch_all=True,
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Webhook not found")
    return rows[0]


def _validate_event_filter(events: list[str] | None) -> str | None:
    if events is None:
        return None
    unknown = {e.upper() for e in events} - _VALID_EVENT_TYPES
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown event types: {', '.join(sorted(unknown))}. "
                   f"Valid: {', '.join(sorted(_VALID_EVENT_TYPES))}",
        )
    return ",".join(e.upper() for e in events)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=WebhookCreated, status_code=status.HTTP_201_CREATED)
async def register_webhook(
    body: WebhookCreate,
    _api_key: str = Depends(get_api_key),
):
    """Register a new webhook endpoint.

    The ``secret`` field in the response is shown **exactly once**.
    Store it immediately — it cannot be retrieved again.  Use it to verify
    the ``X-Sovereign-Signature: sha256=<hmac>`` header on each incoming
    request::

        import hashlib, hmac
        secret = b"<your-secret>"
        raw_body = request.body()
        expected = "sha256=" + hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        assert hmac.compare_digest(request.headers["X-Sovereign-Signature"], expected)
    """
    secret = generate_webhook_secret()
    event_filter_str = _validate_event_filter(body.event_filter)
    url_str = str(body.url)
    now = _now_iso()

    execute_sql(
        """
        INSERT INTO webhook_subscriptions
            (name, url, secret, event_filter, is_active, max_failures,
             consecutive_failures, created_at, updated_at)
        VALUES
            (:name, :url, :secret, :event_filter, 1, :max_failures, 0, :now, :now)
        """,
        {
            "name": body.name,
            "url": url_str,
            "secret": secret,
            "event_filter": event_filter_str,
            "max_failures": body.max_failures,
            "now": now,
        },
    )

    # Fetch back to get the auto-assigned id
    rows = execute_sql(
        "SELECT * FROM webhook_subscriptions WHERE url = :url AND created_at = :now",
        {"url": url_str, "now": now},
        fetch_all=True,
    )
    row = rows[0]
    _log.info("Webhook registered", id=row["id"], name=body.name, url=url_str)

    return WebhookCreated(
        id=row["id"],
        name=row["name"],
        url=row["url"],
        secret=secret,             # shown once
        event_filter=row["event_filter"],
        is_active=bool(row["is_active"]),
        max_failures=row["max_failures"],
        consecutive_failures=row["consecutive_failures"],
        created_at=row["created_at"],
    )


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(_api_key: str = Depends(get_api_key)):
    """List all webhook subscriptions (secrets redacted)."""
    rows = execute_sql(
        "SELECT * FROM webhook_subscriptions ORDER BY created_at DESC",
        fetch_all=True,
    )
    return [
        WebhookOut(
            id=r["id"],
            name=r["name"],
            url=r["url"],
            event_filter=r["event_filter"],
            is_active=bool(r["is_active"]),
            max_failures=r["max_failures"],
            consecutive_failures=r["consecutive_failures"],
            created_at=r["created_at"],
        )
        for r in (rows or [])
    ]


@router.delete("/{sub_id}", status_code=status.HTTP_200_OK)
async def deactivate_webhook(
    sub_id: Annotated[int, Path(ge=1)],
    _api_key: str = Depends(get_api_key),
):
    """Soft-delete a webhook subscription (sets is_active=0).

    Existing dispatch log rows are retained for audit purposes.
    To permanently delete, use the database directly.
    """
    _get_subscription_or_404(sub_id)   # raises 404 if missing
    execute_sql(
        "UPDATE webhook_subscriptions SET is_active = 0, updated_at = :now WHERE id = :id",
        {"id": sub_id, "now": _now_iso()},
    )
    _log.info("Webhook deactivated", id=sub_id)
    return {"id": sub_id, "status": "deactivated"}


@router.post("/{sub_id}/test", status_code=status.HTTP_202_ACCEPTED)
async def test_webhook(
    sub_id: Annotated[int, Path(ge=1)],
    _api_key: str = Depends(get_api_key),
):
    """Fire a synthetic test alert to this endpoint right now.

    Useful for verifying your subscriber is reachable and correctly
    validating the ``X-Sovereign-Signature`` header.
    """
    _get_subscription_or_404(sub_id)

    test_alert = {
        "timestamp": _now_iso(),
        "symbol": "TEST",
        "type": "STOP_LOSS",
        "priority": "CRITICAL",
        "message": "Sovereign webhook test — if you see this, delivery is working.",
        "_test": True,
    }
    await dispatch_alerts([test_alert])
    return {"status": "test_dispatched", "subscription_id": sub_id}


@router.get("/{sub_id}/logs")
async def webhook_logs(
    sub_id: Annotated[int, Path(ge=1)],
    _api_key: str = Depends(get_api_key),
):
    """Last 50 dispatch attempts for a subscription."""
    _get_subscription_or_404(sub_id)
    rows = execute_sql(
        """
        SELECT id, http_status, status, error_detail,
               attempt_count, next_retry_at, dispatched_at
        FROM   alert_dispatch_log
        WHERE  subscription_id = :sid
        ORDER  BY dispatched_at DESC
        LIMIT  50
        """,
        {"sid": sub_id},
        fetch_all=True,
    )
    return rows or []
