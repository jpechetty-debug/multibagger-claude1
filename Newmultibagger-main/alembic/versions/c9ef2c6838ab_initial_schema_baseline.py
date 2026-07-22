"""Initial schema baseline

Revision ID: c9ef2c6838ab
Revises:
Create Date: 2026-05-19 18:08:57.871682

"""
from typing import Union
from collections.abc import Sequence



# revision identifiers, used by Alembic.
revision: str = 'c9ef2c6838ab'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
