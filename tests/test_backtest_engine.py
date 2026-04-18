from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _FakeTrades:
    def win_rate(self):
        return pd.Series({"ABC.NS": 0.60})


class _FakePortfolio:
    trades = _FakeTrades()

    def annualized_return(self):
        return pd.Series({"ABC.NS": 0.12})

    def max_drawdown(self):
        return pd.Series({"ABC.NS": -0.08})

    def sharpe_ratio(self):
        return pd.Series({"ABC.NS": 1.5})


def _load_backtest_engine_module(monkeypatch):
    fake_vbt = types.SimpleNamespace(
        Portfolio=types.SimpleNamespace(from_signals=lambda *args, **kwargs: _FakePortfolio())
    )
    monkeypatch.setitem(sys.modules, "vectorbt", fake_vbt)
    sys.modules.pop("backtest.engine", None)
    return importlib.import_module("backtest.engine")


def test_run_batch_momentum_backtest_handles_suffixing_and_sparse_symbols(monkeypatch):
    backtest_engine_module = _load_backtest_engine_module(monkeypatch)
    dates = pd.date_range("2025-01-01", periods=205)
    abc = pd.DataFrame({"Close": np.linspace(100, 130, len(dates))}, index=dates)
    xyz_close = np.concatenate([np.linspace(50, 60, 145), np.full(60, np.nan)])
    xyz = pd.DataFrame({"Close": xyz_close}, index=dates)
    fake_download = pd.concat({"ABC.NS": abc, "XYZ.NS": xyz}, axis=1)

    monkeypatch.setattr(backtest_engine_module.yf, "download", lambda *args, **kwargs: fake_download)

    engine = backtest_engine_module.VectorBTEngine(period="1y")
    results = engine.run_batch_momentum_backtest(["ABC", "XYZ.NS"])

    assert results["ABC.NS"]["status"] == "OK"
    assert results["ABC.NS"]["cagr"] == 12.0
    assert results["ABC.NS"]["win_rate"] == 60.0
    assert results["ABC.NS"]["max_drawdown"] == -8.0
    assert results["ABC.NS"]["sharpe_ratio"] == 1.5
    assert results["XYZ.NS"]["status"] == "INSUFFICIENT_DATA"
