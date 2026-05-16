from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("xgboost")
pytest.importorskip("shap")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import hybrid_scoring


class _ScoreEchoRegressor:
    def fit(self, X, y):
        return self

    def predict(self, X):
        return pd.to_numeric(X["score"], errors="coerce").fillna(0.0).to_numpy() / 1000.0


def _walk_forward_frame() -> pd.DataFrame:
    rows = []
    quarter_starts = pd.date_range("2024-01-01", periods=6, freq="QS")
    for quarter_idx, as_of_date in enumerate(quarter_starts):
        for symbol_idx, symbol in enumerate(["AAA.NS", "BBB.NS", "CCC.NS"]):
            score = 20 + quarter_idx * 5 + symbol_idx * 10
            row = {feature: 0.0 for feature in hybrid_scoring.FEATURES}
            row.update(
                {
                    "symbol": symbol,
                    "as_of_date": as_of_date,
                    "score": float(score),
                    "forward_return": score / 1000.0,
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def test_walk_forward_validate_uses_expanding_out_of_sample_windows(monkeypatch):
    monkeypatch.setattr(
        hybrid_scoring,
        "_make_xgb_regressor",
        lambda: _ScoreEchoRegressor(),
    )

    metrics = hybrid_scoring.walk_forward_validate(
        _walk_forward_frame(),
        min_train_rows=4,
        min_train_periods=2,
    )

    assert metrics["status"] == "OK"
    assert metrics["folds"] == 4
    assert metrics["rows"] == 12
    assert metrics["spearman_ic"] == pytest.approx(1.0)
    assert metrics["hit_rate"] == pytest.approx(1.0)
    assert [w["train_rows"] for w in metrics["windows"]] == [6, 9, 12, 15]


def test_walk_forward_validate_skips_when_history_is_too_short():
    metrics = hybrid_scoring.walk_forward_validate(
        _walk_forward_frame().head(3),
        min_train_rows=4,
        min_train_periods=2,
    )

    assert metrics["status"] == "SKIPPED"
    assert "not enough" in metrics["reason"]
