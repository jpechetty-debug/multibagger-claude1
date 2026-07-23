"""add shap_top_drivers to multibaggers and create ml_metadata table

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-06-08

Changes
-------
1. multibaggers.shap_top_drivers (Text, nullable)
   ml_ops.batch_update_multibaggers_ml writes the top-5 SHAP driver list
   here as JSON. The column is referenced in ml_ops but was never in the
   schema — every UPDATE silently did nothing.

2. ml_metadata table
   ml_ops.record_training_metadata / get_last_training_info / check_retraining_trigger
   all depend on this table. It is created in code but was never in an
   Alembic migration, so a fresh DB from `alembic upgrade head` was missing
   it and every ml_ops call that tried to INSERT would fail.
"""
from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. shap_top_drivers column ────────────────────────────────────────────
    # SQLite does not support ADD COLUMN IF NOT EXISTS, so we inspect first.
    conn = op.get_bind()
    cols = [row[1] for row in conn.execute(sa.text("PRAGMA table_info(multibaggers)")).fetchall()]
    if "shap_top_drivers" not in cols:
        op.add_column(
            "multibaggers",
            sa.Column("shap_top_drivers", sa.Text, nullable=True),
        )

    # ── 2. ml_metadata table ──────────────────────────────────────────────────
    op.create_table(
        "ml_metadata",
        sa.Column("id",           sa.Integer,   primary_key=True, autoincrement=True),
        sa.Column("trained_at",   sa.DateTime,  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("record_count", sa.Integer,   nullable=True),
        sa.Column("r2_score",     sa.Float,     nullable=True),
        sa.Column("spearman_ic",  sa.Float,     nullable=True),
        sa.Column("hit_rate",     sa.Float,     nullable=True),
        sa.Column("oos_r2",       sa.Float,     nullable=True),
        sa.Column("wf_folds",     sa.Integer,   nullable=True),
        sa.Column("model_path",   sa.Text,      nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ml_metadata")
    # SQLite cannot drop columns; nothing to do for shap_top_drivers on downgrade
