"""Use DATE columns for as_of_date fields

Revision ID: b7c1d2e3f4a5
Revises: c9ef2c6838ab
Create Date: 2026-05-24 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa
from db.date_utils import normalize_date


revision: str = "b7c1d2e3f4a5"
down_revision: Union[str, Sequence[str], None] = "c9ef2c6838ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = {
    "multibaggers": True,
    "fundamentals_pit": False,
    "valuation_metrics": True,
}
def _table_has_column(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    if not inspector.has_table(table_name):
        return False
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _normalize_existing_sqlite_dates(table_name: str, nullable: bool) -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite" or not _table_has_column(bind, table_name, "as_of_date"):
        return

    rows = bind.execute(
        sa.text(f"SELECT rowid, as_of_date FROM {table_name} WHERE as_of_date IS NOT NULL")
    ).fetchall()
    for rowid, raw_value in rows:
        normalized = normalize_date(raw_value, default=str(raw_value))
        if normalized is None and not nullable:
            continue
        if normalized != raw_value:
            bind.execute(
                sa.text(f"UPDATE {table_name} SET as_of_date = :value WHERE rowid = :rowid"),
                {"value": normalized, "rowid": rowid},
            )


def _normalize_existing_sql_dates(table_name: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite" or not _table_has_column(bind, table_name, "as_of_date"):
        return
    op.execute(sa.text(f"UPDATE {table_name} SET as_of_date = CAST(as_of_date AS DATE)"))


def _alter_as_of_date(table_name: str, nullable: bool, target_type) -> None:
    bind = op.get_bind()
    if not _table_has_column(bind, table_name, "as_of_date"):
        return
    kwargs = {}
    if bind.dialect.name == "postgresql" and isinstance(target_type, sa.Date):
        kwargs["postgresql_using"] = "CAST(as_of_date AS DATE)"
    elif bind.dialect.name == "postgresql":
        kwargs["postgresql_using"] = "CAST(as_of_date AS TEXT)"

    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            "as_of_date",
            existing_type=sa.String(),
            type_=target_type,
            existing_nullable=nullable,
            nullable=nullable,
            **kwargs,
        )


def upgrade() -> None:
    for table_name, nullable in _TABLES.items():
        _normalize_existing_sqlite_dates(table_name, nullable)
        _normalize_existing_sql_dates(table_name)
        _alter_as_of_date(table_name, nullable, sa.Date())


def downgrade() -> None:
    for table_name, nullable in _TABLES.items():
        _alter_as_of_date(table_name, nullable, sa.String())
