"""Tests for holdout period module."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.holdout import compare_performance, evaluate_holdout, split_holdout
from modules.hybrid_scoring import FEATURES


def _make_pit_df(start="2016-01-01", periods=24, freq="QS", n_symbols=3, seed=42):
    rng = np.random.RandomState(seed)
    dates = pd.date_range(start, periods=periods, freq=freq)
    rows = []
    for d in dates:
        for i in range(n_symbols):
            row = {f: rng.randn() for f in FEATURES}
            row["symbol"] = f"SYM{i}.NS"
            row["as_of_date"] = d
            row["forward_return"] = rng.randn() * 0.05
            rows.append(row)
    return pd.DataFrame(rows)


def test_split_holdout_no_overlap():
    df = _make_pit_df(start="2016-01-01", periods=24)
    train, holdout = split_holdout(df, "2018-01-01", "2020-12-31")
    train_dates = pd.to_datetime(train["as_of_date"])
    holdout_dates = pd.to_datetime(holdout["as_of_date"])
    assert train_dates.between("2018-01-01", "2020-12-31").sum() == 0
    if not holdout.empty:
        assert holdout_dates.between("2018-01-01", "2020-12-31").all()


def test_split_holdout_empty_when_no_data_in_range():
    df = _make_pit_df(start="2022-01-01", periods=8)
    train, holdout = split_holdout(df, "2018-01-01", "2020-12-31")
    assert holdout.empty
    assert len(train) == len(df)


class _DummyModel:
    def predict(self, X):
        return np.ones(len(X)) * 0.01


def test_evaluate_holdout_returns_metrics():
    df = _make_pit_df(start="2018-01-01", periods=8, n_symbols=5)
    metrics = evaluate_holdout(_DummyModel(), df)
    assert metrics["status"] == "OK"
    assert "oos_r2" in metrics
    assert "spearman_ic" in metrics
    assert metrics["rows"] > 0


def test_evaluate_holdout_empty():
    metrics = evaluate_holdout(_DummyModel(), pd.DataFrame())
    assert metrics["status"] == "NO_HOLDOUT_DATA"


def test_compare_performance_flags_overfitting():
    result = compare_performance(wf_sharpe=1.2, holdout_sharpe=0.5)
    assert result["overfitting_detected"] is True
    assert result["sharpe_gap"] == pytest.approx(0.7, abs=0.01)


def test_compare_performance_passes():
    result = compare_performance(wf_sharpe=0.8, holdout_sharpe=0.7)
    assert result["overfitting_detected"] is False


def test_evaluate_holdout_custom_periods():
    df = _make_pit_df(start="2018-01-01", periods=8, n_symbols=5)
    # Mock model to make predictions different from zero
    class MockPredictor:
        def predict(self, X):
            return np.arange(len(X)) * 0.01

    model = MockPredictor()
    metrics_4 = evaluate_holdout(model, df, periods_per_year=4)
    metrics_12 = evaluate_holdout(model, df, periods_per_year=12)
    assert metrics_4["status"] == "OK"
    assert metrics_12["status"] == "OK"
    assert metrics_4["holdout_sharpe"] != metrics_12["holdout_sharpe"]
    # Ratio should scale by sqrt(12) / sqrt(4) = sqrt(3)
    ratio = metrics_12["holdout_sharpe"] / metrics_4["holdout_sharpe"]
    assert ratio == pytest.approx(np.sqrt(3), abs=0.01)
