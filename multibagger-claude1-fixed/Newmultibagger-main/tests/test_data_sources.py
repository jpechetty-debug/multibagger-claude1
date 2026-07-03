from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.data_service import DataManager


class FakeCache:
    def __init__(self):
        self.values = {}

    def get(self, key: str):
        return self.values.get(key)

    def get_expired(self, key: str):
        return None

    def set(self, key: str, value):
        self.values[key] = value


class FakeProvider:
    available = True
    cooldown_until = 0

    def __init__(self, name: str, payload=None, exc: Exception | None = None):
        self.name = name
        self.payload = payload
        self.exc = exc
        self.calls = 0

    async def safe_fetch(self, symbol: str):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return dict(self.payload)


def complete_payload(symbol: str, source: str):
    return {
        "symbol": symbol,
        "source": source,
        "price": 2450.0,
        "info": {
            "symbol": symbol,
            "marketCap": 10_000_000_000,
            "sector": "Technology",
            "trailingPE": 24.5,
            "returnOnEquity": 0.22,
        },
    }


@pytest.fixture
async def manager():
    dm = DataManager(max_concurrency=1)
    dm.cache = FakeCache()
    try:
        yield dm
    finally:
        await dm.close()


@pytest.mark.asyncio
async def test_fetch_fundamentals_first_provider_success(manager):
    primary = FakeProvider("pnsea", complete_payload("RELIANCE.NS", "pnsea"))
    fallback = FakeProvider("yfinance", complete_payload("RELIANCE.NS", "yfinance"))
    manager.providers = [primary, fallback]

    data = await manager.async_fetch_fundamentals("RELIANCE.NS")

    assert data["symbol"] == "RELIANCE.NS"
    assert data["source"] == "pnsea"
    assert data["data_freshness"] == "live"
    assert primary.calls == 1
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_fetch_fundamentals_falls_back_after_provider_failure(manager):
    failing = FakeProvider("pnsea", exc=TimeoutError("provider timeout"))
    fallback = FakeProvider("nsepython", complete_payload("RELIANCE.NS", "nsepython"))
    manager.providers = [failing, fallback]

    data = await manager.async_fetch_fundamentals("RELIANCE.NS")

    assert data["source"] == "nsepython"
    assert failing.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_fetch_fundamentals_returns_error_when_all_providers_fail(manager):
    manager.providers = [
        FakeProvider("pnsea", exc=RuntimeError("fail")),
        FakeProvider("nsepython", exc=RuntimeError("fail")),
        FakeProvider("yfinance", exc=RuntimeError("fail")),
    ]

    data = await manager.async_fetch_fundamentals("RELIANCE.NS")

    assert data["symbol"] == "RELIANCE.NS"
    assert data["error"] == "All providers failed"
    assert data["source"] == "fallback_failed"
