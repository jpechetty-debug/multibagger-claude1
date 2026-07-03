from __future__ import annotations

import pytest

pytest.importorskip("optuna")
pytest.importorskip("shap")
pytest.importorskip("xgboost")

import pandas as pd

from modules import hybrid_scoring, ml_ops


def test_bootstrap_proxy_uses_fundamentals_when_scores_match():
    df = pd.DataFrame(
        {
            "score": [50, 50],
            "avg_roe_5y": [5, 30],
            "debt_equity": [4, 0],
            "sales_cagr_5y": [0, 100],
        }
    )

    proxy = hybrid_scoring._bootstrap_proxy_return(df)

    assert proxy.iloc[1] > proxy.iloc[0]


def test_bootstrap_upgrade_detection_logs_when_pit_threshold_met(monkeypatch):
    class FakeCursor:
        def fetchone(self):
            return [120]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, _sql):
            return FakeCursor()

    class FakeLogger:
        def __init__(self):
            self.info_calls = []
            self.debug_calls = []

        def info(self, message, **kwargs):
            self.info_calls.append((message, kwargs))

        def debug(self, message):
            self.debug_calls.append(message)

    fake_logger = FakeLogger()
    monkeypatch.setattr(hybrid_scoring, "load_walk_forward_report", lambda: {"is_bootstrap": True})
    monkeypatch.setattr(ml_ops, "get_db_connection", lambda _name: FakeConnection())
    monkeypatch.setattr(ml_ops, "logger", fake_logger)

    pit_count = ml_ops.log_bootstrap_upgrade_availability(min_pit_rows=100)

    assert pit_count == 120
    assert fake_logger.info_calls
    assert fake_logger.info_calls[0][1]["pit_rows"] == 120
