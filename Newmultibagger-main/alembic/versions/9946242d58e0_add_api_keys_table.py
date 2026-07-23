"""add api_keys table

Revision ID: 9946242d58e0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-06 09:26:57.193650

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9946242d58e0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "api_keys",
        sa.Column("key_hash", sa.String(length=64), primary_key=True),
        sa.Column("consumer_name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text('1')),
        sa.Column("rate_limit_rpm", sa.Integer(), nullable=False, server_default=sa.text('60')),
        sa.Column("total_usage", sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now())
    )

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("api_keys")
