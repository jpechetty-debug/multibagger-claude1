from __future__ import annotations

import asyncio
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import modules.data_service as data_service_module


def test_pnsea_provider_initializes_client_lazily(monkeypatch):
    calls = []

    class FakeNSEClient:
        def __init__(self):
            self.equity = SimpleNamespace(
                info=lambda symbol: {
                    "priceInfo": {"lastPrice": 2450.0},
                    "info": {
                        "roe": 22.0,
                        "salesGrowth": 14.0,
                        "promoterHolding": 52.0,
                        "fiiHolding": 18.0,
                        "diiHolding": 11.0,
                    },
                }
            )
            self.insider = SimpleNamespace(
                getPledgedData=lambda symbol: {"pledgedPercentage": 1.5}
            )

    def factory():
        calls.append("created")
        return FakeNSEClient()

    fake_ticker = SimpleNamespace(
        financials=pd.DataFrame(),
        balance_sheet=pd.DataFrame(),
        cash_flow=pd.DataFrame(),
    )
    monkeypatch.setattr(data_service_module.yf, "Ticker", lambda symbol: fake_ticker)

    executor = ThreadPoolExecutor(max_workers=1)
    try:
        provider = data_service_module.PNSEAProvider(executor, nse_factory=factory)
        assert calls == []

        payload = asyncio.run(provider.fetch_fundamentals("TCS.NS"))
        payload_again = asyncio.run(provider.fetch_fundamentals("TCS.NS"))

        assert calls == ["created"]
        assert payload["source"] == "pnsea"
        assert payload["price"] == 2450.0
        assert payload_again["pledge_percent"] == 1.5
    finally:
        executor.shutdown(wait=True)
