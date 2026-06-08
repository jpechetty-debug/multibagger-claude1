"""add webhook_subscriptions and alert_dispatch_log tables

Revision ID: e1f2a3b4c5d6
Revises: 9946242d58e0
Create Date: 2026-06-08

Two new tables:

webhook_subscriptions
  One row per registered endpoint.  The ``secret`` column stores a
  32-byte hex HMAC secret used to sign outgoing payloads.  Consumers
  verify the ``X-Sovereign-Signature`` header with this secret.

alert_dispatch_log
  Append-only delivery log.  Every dispatch attempt (success or failure)
  writes a row so the retry worker can pick up outstanding failures without
  a separate queue service.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e1f2a3b4c5d6"
down_revision = "9946242d58e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "webhook_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        # Subscriber-chosen label — used in logs and UI only.
        sa.Column("name", sa.String(120), nullable=False),
        # The HTTPS endpoint we POST alerts to.
        sa.Column("url", sa.Text, nullable=False),
        # 64-char hex (32 bytes) HMAC secret.  Generated server-side on
        # registration; shown to the caller once, never again.
        sa.Column("secret", sa.String(64), nullable=False),
        # Comma-separated alert types to include: STOP_LOSS,THESIS_BREAK,PRICE_DRIFT,REGIME_SHIFT
        # NULL = receive all types.
        sa.Column("event_filter", sa.Text, nullable=True),
        # Soft-delete: set is_active=0 to disable without losing config.
        sa.Column("is_active", sa.Integer, nullable=False, server_default="1"),
        # Retry budget: max consecutive failures before auto-disabling.
        sa.Column("max_failures", sa.Integer, nullable=False, server_default="5"),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    op.create_index("idx_wh_active", "webhook_subscriptions", ["is_active"])

    op.create_table(
        "alert_dispatch_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "subscription_id",
            sa.Integer,
            sa.ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The full JSON payload we sent (or attempted to send).
        sa.Column("payload", sa.Text, nullable=False),
        # HTTP status code returned by the subscriber, or NULL on network error.
        sa.Column("http_status", sa.Integer, nullable=True),
        # 'delivered' | 'failed' | 'pending'
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_retry_at", sa.DateTime, nullable=True),
        sa.Column("dispatched_at", sa.DateTime, nullable=False),
    )
    op.create_index(
        "idx_adl_pending_retry",
        "alert_dispatch_log",
        ["status", "next_retry_at"],
    )
    op.create_index(
        "idx_adl_subscription",
        "alert_dispatch_log",
        ["subscription_id", "dispatched_at"],
    )


def downgrade() -> None:
    op.drop_table("alert_dispatch_log")
    op.drop_table("webhook_subscriptions")
