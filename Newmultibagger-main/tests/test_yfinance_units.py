"""yfinance fundamentals: unit conversion and missing-value handling (offline)."""

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pandas as pd
import pytest

import modules.adapters.yfinance as yf_adapter
from modules.adapters.yfinance import YFinanceProvider, _cfo_pat_ratio, _scaled


def _fetch(monkeypatch, info: dict) -> dict:
    fake = SimpleNamespace(
        info=info,
        fast_info=None,
        financials=pd.DataFrame(),
        balance_sheet=pd.DataFrame(),
        cash_flow=pd.DataFrame(),
    )
    monkeypatch.setattr(yf_adapter.yf, "Ticker", lambda _symbol: fake)
    return asyncio.run(YFinanceProvider(ThreadPoolExecutor(1)).fetch_fundamentals("TCS.NS"))


def test_units_converted(monkeypatch):
    out = _fetch(monkeypatch, {
        "currentPrice": 2114.4,
        "returnOnEquity": 0.47743,
        "revenueGrowth": 0.05,
        "debtToEquity": 10.211,  # yfinance percentage → 0.102 ratio
        "operatingCashflow": 523_459_985_408,
        "netIncomeToCommon": 497_990_008_832,
    })
    assert out["ROE%"] == pytest.approx(47.743)
    assert out["Sales_Growth_TTM%"] == pytest.approx(5.0)
    assert out["Debt_Equity"] == pytest.approx(0.1021, abs=1e-4)
    assert out["CFO_PAT_Ratio"] == pytest.approx(1.051, abs=1e-3)


def test_missing_values_stay_none(monkeypatch):
    out = _fetch(monkeypatch, {"currentPrice": 100.0, "returnOnEquity": float("nan")})
    for key in ("ROE%", "Sales_Growth_TTM%", "Debt_Equity", "CFO_PAT_Ratio"):
        assert out[key] is None, key


def test_helpers_reject_non_finite_and_loss_makers():
    assert _scaled(None, 100) is None
    assert _scaled(float("inf"), 100) is None
    assert _scaled("bad", 100) is None
    assert _cfo_pat_ratio(100.0, -50.0) is None
    assert _cfo_pat_ratio(float("nan"), 50.0) is None
    assert math.isclose(_cfo_pat_ratio(60.0, 50.0), 1.2)
