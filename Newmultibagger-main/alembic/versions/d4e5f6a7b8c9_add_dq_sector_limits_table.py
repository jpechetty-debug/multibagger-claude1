"""Add dq_sector_limits table

Revision ID: d4e5f6a7b8c9
Revises: b7c1d2e3f4a5
Create Date: 2026-05-26 10:47:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "b7c1d2e3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dq_sector_limits",
        sa.Column("sector", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("min_val", sa.Float(), nullable=False),
        sa.Column("max_val", sa.Float(), nullable=False),
        sa.Column("auto_scale_threshold", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("sector", "metric"),
    )


def downgrade() -> None:
    op.drop_table("dq_sector_limits")
