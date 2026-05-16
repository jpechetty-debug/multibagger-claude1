from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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
    assert abs(results["ABC.NS"]["gross_cagr"] - 13.21) < 0.1
    gross_returns = abc["Close"].pct_change().shift(-1).dropna()
    entry_turnover = pd.Series(0.0, index=gross_returns.index)
    entry_turnover.iloc[0] = 1.0
    net_returns = backtest_engine_module.apply_transaction_costs(
        gross_returns,
        entry_turnover,
        engine.transaction_cost,
    )
    expected_net_cagr = (np.prod(1 + net_returns) ** (12 / len(net_returns)) - 1) * 100
    assert abs(results["ABC.NS"]["cagr"] - expected_net_cagr) < 0.1
    assert results["ABC.NS"]["cagr"] < results["ABC.NS"]["gross_cagr"]
    assert results["ABC.NS"]["transaction_cost_drag"] > 0
    assert results["ABC.NS"]["turnover"] == 1.0
    assert results["ABC.NS"]["benchmark_symbol"] == "^CNX500"
    assert results["ABC.NS"]["benchmark_status"] == "NO_DATA"
    assert results["ABC.NS"]["win_rate"] == 100.0
    assert results["ABC.NS"]["max_drawdown"] == 0.0
    assert results["XYZ.NS"]["status"] == "INSUFFICIENT_DATA"


def test_apply_transaction_costs_charges_only_turnover(monkeypatch):
    backtest_engine_module = _load_backtest_engine_module(monkeypatch)

    gross = pd.Series([0.02, 0.01, -0.03])
    turnover = pd.Series([1.0, 0.0, 0.5])

    net = backtest_engine_module.apply_transaction_costs(gross, turnover, transaction_cost=0.006)

    assert np.allclose(net.to_numpy(), [0.014, 0.01, -0.033])


def test_benchmark_metrics_aligns_returns_and_reports_relative_stats(monkeypatch):
    backtest_engine_module = _load_backtest_engine_module(monkeypatch)

    idx = pd.period_range("2025-01", periods=4, freq="M")
    strategy = pd.Series([0.03, 0.02, -0.01, 0.04], index=idx)
    benchmark = pd.Series([0.01, 0.01, -0.02, 0.02], index=idx)

    metrics = backtest_engine_module.benchmark_metrics(strategy, benchmark)

    assert metrics["benchmark_status"] == "OK"
    assert metrics["benchmark_cagr"] > 0
    assert metrics["alpha_cagr"] > 0
    assert metrics["alpha_monthly"] > 0
    assert np.isfinite(metrics["beta"])
    assert metrics["tracking_error"] > 0
    assert metrics["information_ratio"] > 0


def test_run_batch_momentum_backtest_includes_benchmark_relative_metrics(monkeypatch):
    backtest_engine_module = _load_backtest_engine_module(monkeypatch)

    dummy_scores = pd.DataFrame({
        "symbol": ["ABC.NS"],
        "as_of_date": ["2025-01-01"],
        "score": [80.0]
    })
    monkeypatch.setattr(pd, "read_sql_query", lambda *args, **kwargs: dummy_scores)

    dates = pd.date_range("2025-01-01", periods=12, freq="ME")
    abc = pd.DataFrame({"Close": np.linspace(100, 112, len(dates))}, index=dates)
    benchmark = pd.DataFrame({"Close": np.linspace(100, 106, len(dates))}, index=dates)
    fake_download = pd.concat({"ABC.NS": abc, "^CNX500": benchmark}, axis=1)

    monkeypatch.setattr(
        backtest_engine_module.yf, "download", lambda *args, **kwargs: fake_download
    )

    engine = backtest_engine_module.VectorBTEngine(period="1y")
    results = engine.run_batch_momentum_backtest(["ABC.NS"])
    abc_result = results["ABC.NS"]

    assert abc_result["benchmark_status"] == "OK"
    assert abc_result["benchmark_symbol"] == "^CNX500"
    assert abc_result["benchmark_cagr"] > 0
    assert abc_result["alpha_cagr"] == pytest.approx(
        abc_result["cagr"] - abc_result["benchmark_cagr"]
    )
    assert np.isfinite(abc_result["beta"])
    assert abc_result["tracking_error"] >= 0


class _ScoreModel:
    def fit(self, X, y):
        return self

    def predict(self, X):
        return pd.to_numeric(X["score"], errors="coerce").fillna(0.0).to_numpy()


def _prices_from_returns(returns):
    prices = [100.0]
    for ret in returns:
        prices.append(prices[-1] * (1 + ret))
    return prices


def test_walk_forward_strategy_backtest_trains_past_only_and_reports_portfolio_metrics(
    monkeypatch,
):
    backtest_engine_module = _load_backtest_engine_module(monkeypatch)
    feature_cols = backtest_engine_module.DEFAULT_WALK_FORWARD_FEATURES

    monkeypatch.setattr(backtest_engine_module, "_make_walk_forward_model", lambda: _ScoreModel())
    monkeypatch.setattr(
        backtest_engine_module,
        "_sanitize_walk_forward_features",
        lambda df: df.apply(pd.to_numeric, errors="coerce").fillna(0.0),
    )

    price_dates = pd.date_range("2024-01-31", periods=9, freq="ME")
    pit_dates = price_dates[:-1]
    rows = []
    score_map = {"AAA.NS": 90.0, "BBB.NS": 50.0, "CCC.NS": 10.0}
    for date in pit_dates:
        for symbol, score in score_map.items():
            row = {feature: 0.0 for feature in feature_cols}
            row.update({"symbol": symbol, "as_of_date": date.strftime("%Y-%m-%d"), "score": score})
            rows.append(row)
    pit_df = pd.DataFrame(rows)
    monkeypatch.setattr(pd, "read_sql_query", lambda *args, **kwargs: pit_df)

    fake_download = pd.concat(
        {
            "AAA.NS": pd.DataFrame(
                {"Close": _prices_from_returns([0.03] * 8)}, index=price_dates
            ),
            "BBB.NS": pd.DataFrame(
                {"Close": _prices_from_returns([0.01] * 8)}, index=price_dates
            ),
            "CCC.NS": pd.DataFrame(
                {"Close": _prices_from_returns([-0.01] * 8)}, index=price_dates
            ),
            "^CNX500": pd.DataFrame(
                {"Close": _prices_from_returns([0.005] * 8)}, index=price_dates
            ),
        },
        axis=1,
    )
    monkeypatch.setattr(
        backtest_engine_module.yf, "download", lambda *args, **kwargs: fake_download
    )

    engine = backtest_engine_module.VectorBTEngine(period="1y")
    result = engine.run_walk_forward_strategy_backtest(
        ["AAA", "BBB", "CCC"],
        min_train_periods=3,
        rebalance_frequency="monthly",
        top_quantile=0.67,
    )

    assert result["status"] == "OK"
    assert result["strategy"] == "xgboost_walk_forward"
    assert result["rebalance_frequency"] == "M"
    assert result["folds"] == 5
    assert result["gross_cagr"] > result["cagr"]
    assert result["transaction_cost_drag"] > 0
    assert result["benchmark_status"] == "OK"
    assert result["alpha_cagr"] > 0
    assert result["turnover"] == pytest.approx(1.0)
    assert result["avg_turnover"] == pytest.approx(0.2)

    for fold in result["fold_details"]:
        assert fold["selected_symbols"] == ["AAA.NS"]
        assert pd.Period(fold["train_end_period"], freq="M") < pd.Period(
            fold["test_period"], freq="M"
        )
