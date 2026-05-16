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

    # Mock pd.read_sql_query to return non-empty scores
    dummy_scores = pd.DataFrame({
        "symbol": ["ABC.NS"],
        "as_of_date": ["2025-01-01"],
        "score": [80.0]
    })
    monkeypatch.setattr(pd, "read_sql_query", lambda *args, **kwargs: dummy_scores)

    dates = pd.date_range("2025-01-01", periods=12, freq="ME")
    abc = pd.DataFrame({"Close": np.linspace(100, 112, len(dates))}, index=dates)
    xyz_close = np.full(12, np.nan)
    xyz = pd.DataFrame({"Close": xyz_close}, index=dates)
    fake_download = pd.concat({"ABC.NS": abc, "XYZ.NS": xyz}, axis=1)

    monkeypatch.setattr(
        backtest_engine_module.yf, "download", lambda *args, **kwargs: fake_download
    )

    engine = backtest_engine_module.VectorBTEngine(period="1y")
    results = engine.run_batch_momentum_backtest(["ABC", "XYZ.NS"])

    assert results["ABC.NS"]["status"] == "OK"
    # Expected CAGR calculation: Total return is 12% over 12 months.
    # returns.pct_change().shift(-1) yields 11 valid returns.
    # CAGR = (1.12 ** (12 / 11) - 1) * 100 = 13.21...
    assert abs(results["ABC.NS"]["cagr"] - 13.21) < 0.1
    assert results["ABC.NS"]["win_rate"] == 100.0
    assert results["ABC.NS"]["max_drawdown"] == 0.0
    assert results["XYZ.NS"]["status"] == "INSUFFICIENT_DATA"
