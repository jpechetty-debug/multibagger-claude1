from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.data_layer.data_service import (
    ScreenerRepository,
    ScreenerRow,
    _postgres_dsn_for_asyncpg,
    validate_screener_schema,
)


def test_screener_row_preserves_missing_financials_as_none():
    row = ScreenerRow.model_validate(
        {
            "Symbol": "TEST.NS",
            "Price": "",
            "ROE%": None,
            "PE_Ratio": "nan",
            "Debt_Equity": "--",
            "Market_Cap_Cr": "1,234.5",
            "F_Score": "6.0",
        }
    )

    assert row.price is None
    assert row.roe is None
    assert row.pe_ratio is None
    assert row.debt_equity is None
    assert row.market_cap_cr == pytest.approx(1234.5)
    assert row.f_score == 6


def test_schema_validation_is_lru_cached_for_columns_only():
    validate_screener_schema.cache_clear()

    assert validate_screener_schema(("Symbol", "Price")) == ("symbol", "price")
    assert validate_screener_schema(("Symbol", "Price")) == ("symbol", "price")

    cache_info = validate_screener_schema.cache_info()
    assert cache_info.maxsize == 1
    assert cache_info.hits == 1
    assert cache_info.misses == 1


@pytest.mark.asyncio
async def test_repository_csv_fallback_reads_and_validates_rows(tmp_path, monkeypatch):
    csv_path = tmp_path / "screener_results.csv"
    csv_path.write_text(
        "Symbol,Price,PE_Ratio,F_Score\n"
        "TCS.NS,3810.5,28.2,7\n"
        "INFY.NS,,--,\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("USE_CSV_FALLBACK", "1")

    rows = await ScreenerRepository(csv_path=csv_path).fetch_rows(limit=2)

    assert [row.symbol for row in rows] == ["TCS.NS", "INFY.NS"]
    assert rows[0].pe_ratio == pytest.approx(28.2)
    assert rows[1].price is None
    assert rows[1].pe_ratio is None
    assert rows[1].f_score is None


def test_sqlite_url_is_rejected_for_production_repository():
    with pytest.raises(ValueError, match="Neon PostgreSQL, not SQLite"):
        _postgres_dsn_for_asyncpg("sqlite:///stocks.db")


@pytest.mark.asyncio
async def test_repository_reads_neon_with_asyncpg(monkeypatch):
    captured = {}

    class FakePrepared:
        def get_attributes(self):
            return [SimpleNamespace(name="symbol"), SimpleNamespace(name="price")]

    class FakeConnection:
        async def prepare(self, query):
            captured["prepare_query"] = query
            return FakePrepared()

        async def fetch(self, query, *args):
            captured["fetch_query"] = query
            captured["fetch_args"] = args
            return [{"symbol": "RELIANCE.NS", "price": "1336.4"}]

        async def close(self):
            captured["closed"] = True

    class FakeConnectionContext:
        async def __aenter__(self):
            return FakeConnection()
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            captured["closed"] = True

    class FakePool:
        def acquire(self):
            return FakeConnectionContext()

    async def fake_create_pool(dsn, **kwargs):
        captured["dsn"] = dsn
        return FakePool()

    async def fake_connect(*, dsn):
        captured["dsn"] = dsn
        return FakeConnection()

    monkeypatch.delenv("USE_CSV_FALLBACK", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "asyncpg",
        SimpleNamespace(connect=fake_connect, create_pool=fake_create_pool),
    )

    rows = await ScreenerRepository(
        database_url="postgresql+psycopg://user:pass@example.test/neondb",
        table_name="public.multibaggers",
    ).fetch_rows(limit=1)

    assert captured["dsn"].startswith("postgresql://")
    assert captured["prepare_query"] == 'SELECT * FROM "public"."multibaggers" LIMIT 0'
    assert captured["fetch_query"] == 'SELECT * FROM "public"."multibaggers" LIMIT $1'
    assert captured["fetch_args"] == (1,)
    assert captured["closed"] is True
    assert rows[0].symbol == "RELIANCE.NS"
    assert rows[0].price == pytest.approx(1336.4)
