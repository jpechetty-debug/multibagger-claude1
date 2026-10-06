"""Guard against runtime-only schema: Alembic autogenerate drops anything the models lack."""

import re
from pathlib import Path

from db import models

ROOT = Path(__file__).resolve().parents[1]


def _declared() -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for mapper in models.Base.registry.mappers:
        table = mapper.local_table
        tables.setdefault(table.name, set()).update(c.name for c in table.columns)
    return tables


def test_every_runtime_added_column_is_declared_in_models():
    source = (ROOT / "db" / "repository.py").read_text(encoding="utf-8")
    added = re.findall(r'_ensure_column\(\s*conn,\s*"(\w+)",\s*"(\w+)"', source)
    assert added, "pattern no longer matches _ensure_column calls"
    declared = _declared()
    missing = [(t, c) for t, c in added if c not in declared.get(t, set())]
    assert not missing, f"add these to db/models.py or autogenerate will drop them: {missing}"


def test_runtime_created_tables_are_declared():
    source = (ROOT / "db" / "repository.py").read_text(encoding="utf-8")
    created = set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", source))
    missing = created - set(_declared())
    assert not missing, f"add models for these tables or autogenerate will drop them: {missing}"
