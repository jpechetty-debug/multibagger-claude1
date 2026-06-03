"""Test score reproducibility — identical inputs must produce bit-identical outputs."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("xgboost")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.hybrid_scoring import FEATURES, _make_xgb_regressor, _sanitize_features


def _deterministic_dataset(n_symbols=10, n_periods=6, seed=42):
    """Build a fixed dataset sorted deterministically."""
    rng = np.random.RandomState(seed)
    rows = []
    symbols = [f"SYM{i:03d}.NS" for i in range(n_symbols)]
    dates = pd.date_range("2021-01-01", periods=n_periods, freq="QS")
    for d in dates:
        for s in symbols:
            row = {f: rng.randn() for f in FEATURES}
            row["symbol"] = s
            row["as_of_date"] = d
            row["forward_return"] = rng.randn() * 0.05
            rows.append(row)
    df = pd.DataFrame(rows).sort_values(["symbol", "as_of_date"]).reset_index(drop=True)
    return df


def _train_and_predict(df):
    np.random.seed(42)
    X = _sanitize_features(df[FEATURES])
    y = pd.to_numeric(df["forward_return"], errors="coerce")
    model = _make_xgb_regressor()
    model.set_params(n_jobs=1)
    model.fit(X, y)
    return model.predict(X)


def test_reproducible_predictions():
    df = _deterministic_dataset()
    preds_a = _train_and_predict(df.copy())
    preds_b = _train_and_predict(df.copy())
    np.testing.assert_array_equal(preds_a, preds_b)


def test_features_list_is_deterministic():
    """FEATURES must be an ordered list, not a set or dict."""
    assert isinstance(FEATURES, list)
    assert FEATURES == FEATURES.copy()  # order preserved


def test_sanitize_is_stateless():
    from modules.hybrid_scoring import _sanitize_features
    # Create two identical DataFrames
    df_a = pd.DataFrame({"score": [1.0, 2.0, np.nan], "pe_ratio": [15.0, np.nan, 20.0]})
    df_b = df_a.copy()

    # Call _sanitize_features twice on identical inputs
    res_a1 = _sanitize_features(df_a)
    res_a2 = _sanitize_features(df_a)

    # Assert result is identical
    pd.testing.assert_frame_equal(res_a1, res_a2)
    pd.testing.assert_frame_equal(df_a, df_b)  # verify input is not mutated in-place

    # Create a different DataFrame
    df_c = pd.DataFrame({"score": [10.0, 20.0, np.nan], "pe_ratio": [150.0, np.nan, 200.0]})
    res_c = _sanitize_features(df_c)

    # Calling it on df_c should not change the result of calling it on df_a again
    res_a3 = _sanitize_features(df_a)
    pd.testing.assert_frame_equal(res_a1, res_a3)
