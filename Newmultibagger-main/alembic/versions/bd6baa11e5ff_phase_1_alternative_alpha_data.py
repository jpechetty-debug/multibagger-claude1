"""phase_1_alternative_alpha_data

Revision ID: bd6baa11e5ff
Revises: f1a2b3c4d5e6
Create Date: 2026-06-13 11:51:29.562568

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd6baa11e5ff'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fundamentals_pit', sa.Column('ocf_yield', sa.Float(), nullable=True))
    op.add_column('fundamentals_pit', sa.Column('earnings_velocity_qoq', sa.Float(), nullable=True))
    op.add_column('fundamentals_pit', sa.Column('earnings_velocity_yoy', sa.Float(), nullable=True))

    op.add_column('multibaggers', sa.Column('ocf_yield', sa.Float(), nullable=True))
    op.add_column('multibaggers', sa.Column('earnings_velocity_qoq', sa.Float(), nullable=True))
    op.add_column('multibaggers', sa.Column('earnings_velocity_yoy', sa.Float(), nullable=True))

    op.create_table('institutional_flows',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('symbol', sa.String(), nullable=False),
    sa.Column('execution_date', sa.Date(), nullable=False),
    sa.Column('transaction_type', sa.String(), nullable=True),
    sa.Column('party_name', sa.String(), nullable=True),
    sa.Column('quantity', sa.Float(), nullable=True),
    sa.Column('price_per_share', sa.Float(), nullable=True),
    sa.Column('value_cr', sa.Float(), nullable=True),
    sa.Column('reported_at', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_inst_flows_sym_date', 'institutional_flows', ['symbol', 'execution_date'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_inst_flows_sym_date', table_name='institutional_flows')
    op.drop_table('institutional_flows')

    op.drop_column('multibaggers', 'earnings_velocity_yoy')
    op.drop_column('multibaggers', 'earnings_velocity_qoq')
    op.drop_column('multibaggers', 'ocf_yield')

    op.drop_column('fundamentals_pit', 'earnings_velocity_yoy')
    op.drop_column('fundamentals_pit', 'earnings_velocity_qoq')
    op.drop_column('fundamentals_pit', 'ocf_yield')
