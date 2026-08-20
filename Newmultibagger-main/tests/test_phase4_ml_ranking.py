"""Tests for Phase 4: Hybrid Machine Learning Ranking.

Covers:
  - Module 4.1: Optuna Bayesian hyperparameter optimization (warm-start, convergence)
  - Module 4.2 & 4.3: SHAP dominance guard (rejection of single-feature-dominated models)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("xgboost")
pytest.importorskip("shap")
pytest.importorskip("optuna")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import xgboost as xgb  # noqa: E402

from modules.scoring.ml_score import (  # noqa: E402
    FEATURES,
    SHAP_DOMINANCE_THRESHOLD,
    _make_xgb_regressor,
    _sanitize_features,
    check_shap_dominance,
    optuna_optimize,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_synthetic_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Build a synthetic training frame with FEATURES + forward_return."""
    rng = np.random.default_rng(seed)
    data = {feat: rng.uniform(0, 1, n) for feat in FEATURES}
    # Forward return is a blend of features (no single-feature dominance)
    data["forward_return"] = (
        data["score"] * 0.3
        + data["avg_roe_5y"] * 0.25
        + data["ret_6m"] * 0.2
        + data["pe_ratio"] * -0.15
        + rng.normal(0, 0.05, n)
    )
    data["symbol"] = [f"S{i}" for i in range(n)]
    data["as_of_date"] = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame(data)


def _make_leaky_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Build a frame where forward_return is almost entirely explained by 'score'."""
    rng = np.random.default_rng(seed)
    data = {feat: rng.uniform(0, 1, n) for feat in FEATURES}
    # Make forward_return almost perfectly correlated with 'score' alone
    data["forward_return"] = data["score"] * 0.99 + rng.normal(0, 0.001, n)
    data["symbol"] = [f"S{i}" for i in range(n)]
    data["as_of_date"] = pd.date_range("2023-01-01", periods=n, freq="D")
    return pd.DataFrame(data)


# ── Module 4.1: Optuna Bayesian Search ─────────────────────────────────────


class TestOptunaOptimize:
    """Tests for the Optuna Bayesian hyperparameter search."""

    def test_returns_valid_params_dict(self):
        df = _make_synthetic_df(60)
        best = optuna_optimize(df, n_trials=3, cv_folds=2, timeout_seconds=60)
        required_keys = {
            "n_estimators", "learning_rate", "max_depth", "subsample",
            "colsample_bytree", "min_child_weight", "reg_alpha", "reg_lambda",
            "random_state", "eval_metric",
        }
        assert required_keys.issubset(set(best.keys()))

    def test_warm_start_legacy_params_included(self):
        df = _make_synthetic_df(60)
        # With n_trials=1, only the warm-start (legacy params) trial runs
        best = optuna_optimize(df, n_trials=1, cv_folds=2, timeout_seconds=30)
        assert isinstance(best, dict)
        assert best["random_state"] == 42

    def test_produces_valid_xgb_regressor(self):
        df = _make_synthetic_df(60)
        best = optuna_optimize(df, n_trials=2, cv_folds=2, timeout_seconds=30)
        model = _make_xgb_regressor(best)
        assert isinstance(model, xgb.XGBRegressor)

    def test_model_from_optimized_params_can_train(self):
        df = _make_synthetic_df(60)
        best = optuna_optimize(df, n_trials=2, cv_folds=2, timeout_seconds=30)
        model = _make_xgb_regressor(best)
        X = _sanitize_features(df[FEATURES])
        y = df["forward_return"].values
        model.fit(X, y)
        preds = model.predict(X)
        assert len(preds) == len(X)
        assert all(np.isfinite(preds))


# ── Module 4.2 & 4.3: SHAP Dominance Guard ────────────────────────────────


class TestSHAPDominanceGuard:
    """Tests for check_shap_dominance."""

    def test_balanced_model_passes(self):
        df = _make_synthetic_df(80)
        X = _sanitize_features(df[FEATURES])
        y = df["forward_return"].values
        model = xgb.XGBRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)

        passes, reason, importance = check_shap_dominance(model, X)
        assert passes is True
        assert reason == "OK"
        assert len(importance) == len(FEATURES)
        # No single feature should dominate >90%
        assert max(importance.values()) <= SHAP_DOMINANCE_THRESHOLD

    def test_single_feature_model_rejected(self):
        df = _make_leaky_df(80)
        X = _sanitize_features(df[FEATURES])
        y = df["forward_return"].values
        model = xgb.XGBRegressor(n_estimators=100, max_depth=6, random_state=42)
        model.fit(X, y)

        passes, reason, importance = check_shap_dominance(model, X, threshold=0.90)
        assert passes is False
        assert "REJECTED" in reason
        assert "score" in reason  # 'score' should be the dominant feature

    def test_custom_threshold(self):
        df = _make_synthetic_df(80)
        X = _sanitize_features(df[FEATURES])
        y = df["forward_return"].values
        model = xgb.XGBRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)

        # With a very tight threshold (10%), even a balanced model might fail
        passes_tight, _, imp = check_shap_dominance(model, X, threshold=0.10)
        # With a very lax threshold (99%), everything passes
        passes_lax, _, _ = check_shap_dominance(model, X, threshold=0.99)
        assert passes_lax is True

    def test_importance_sums_to_one(self):
        df = _make_synthetic_df(60)
        X = _sanitize_features(df[FEATURES])
        y = df["forward_return"].values
        model = xgb.XGBRegressor(n_estimators=30, random_state=42)
        model.fit(X, y)

        _, _, importance = check_shap_dominance(model, X)
        total = sum(importance.values())
        assert total == pytest.approx(1.0, abs=0.01)

    def test_sample_size_parameter(self):
        df = _make_synthetic_df(200)
        X = _sanitize_features(df[FEATURES])
        y = df["forward_return"].values
        model = xgb.XGBRegressor(n_estimators=20, random_state=42)
        model.fit(X, y)

        # Should work with sample_size smaller than dataset
        passes, _, _ = check_shap_dominance(model, X, sample_size=10)
        assert isinstance(passes, bool)


# ── Integration: _make_xgb_regressor with custom params ───────────────────


class TestMakeXGBRegressorWithParams:
    """Tests for the updated _make_xgb_regressor that accepts params."""

    def test_default_params(self):
        model = _make_xgb_regressor()
        assert model.get_params()["max_depth"] == 4
        assert model.get_params()["n_estimators"] == 100

    def test_custom_params_override(self):
        model = _make_xgb_regressor({"max_depth": 6, "n_estimators": 200})
        assert model.get_params()["max_depth"] == 6
        assert model.get_params()["n_estimators"] == 200
        # Other defaults should still be present
        assert model.get_params()["subsample"] == 0.8

    def test_none_params_uses_defaults(self):
        model = _make_xgb_regressor(None)
        assert model.get_params()["max_depth"] == 4
