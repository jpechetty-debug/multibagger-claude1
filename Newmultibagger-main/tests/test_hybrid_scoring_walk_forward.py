# tests/test_hybrid_scoring_walk_forward.py
# Sovereign AI — XGBoost Hybrid Scorer: comprehensive test suite
# Tests: walk-forward validation, stateless sanitize, SHAP explain,
#        batch predict, holdout evaluation, IC monitor, leakage audit.

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("xgboost")
pytest.importorskip("shap")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules import hybrid_scoring  # noqa: E402
from modules.scoring.ml_score import (  # noqa: E402
    FEATURE_BOUNDS,
    FEATURES,
    HOLDOUT_END,
    HOLDOUT_START,
    _alias_factors,
    _finite_or_none,
    _sanitize_features,
    _spearman_ic,
    _top_quantile_sharpe,
    walk_forward_validate,
)

# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

class _ScoreEchoRegressor:
    """Deterministic stub that returns score / 1000 as the predicted return."""

    def fit(self, X, y, **kwargs):
        return self

    def predict(self, X):
        return pd.to_numeric(X["score"], errors="coerce").fillna(0.0).to_numpy() / 1000.0


def _make_wf_frame(
    n_quarters: int = 6,
    symbols: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a synthetic PIT frame suitable for walk_forward_validate."""
    rng = np.random.default_rng(seed)
    symbols = symbols or ["AAA.NS", "BBB.NS", "CCC.NS"]
    quarter_starts = pd.date_range("2024-01-01", periods=n_quarters, freq="QS")
    rows = []
    for q_idx, as_of_date in enumerate(quarter_starts):
        for s_idx, symbol in enumerate(symbols):
            score = 20.0 + q_idx * 5 + s_idx * 10
            row = dict.fromkeys(FEATURES, 0.0)
            row.update(
                {
                    "symbol":         symbol,
                    "as_of_date":     as_of_date,
                    "score":          float(score),
                    "forward_return": score / 1000.0 + rng.normal(0, 0.001),
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# _sanitize_features
# ---------------------------------------------------------------------------

class TestSanitizeFeatures:
    def test_returns_only_feature_columns(self):
        df = pd.DataFrame([dict.fromkeys(FEATURES, 1.0) | {"extra_col": 99.9}])
        result = _sanitize_features(df)
        assert list(result.columns) == FEATURES

    def test_fills_missing_columns_with_nan(self):
        df = pd.DataFrame([{"score": 50.0}])
        result = _sanitize_features(df)
        assert np.isnan(result["sales_cagr_5y"].iloc[0])

    def test_clips_to_feature_bounds(self):
        df = pd.DataFrame([{"score": 9999.0, "pe_ratio": -999.0}])
        result = _sanitize_features(df)
        lo_s, hi_s = FEATURE_BOUNDS["score"]
        lo_p, hi_p = FEATURE_BOUNDS["pe_ratio"]
        assert result["score"].iloc[0]    == hi_s
        assert result["pe_ratio"].iloc[0] == lo_p

    def test_replaces_inf_with_nan(self):
        df = pd.DataFrame([{"ret_6m": np.inf, "ret_3m": -np.inf}])
        result = _sanitize_features(df)
        assert np.isnan(result["ret_6m"].iloc[0])
        assert np.isnan(result["ret_3m"].iloc[0])

    def test_replaces_nan_with_nan(self):
        df = pd.DataFrame([{"avg_roe_5y": np.nan}])
        result = _sanitize_features(df)
        assert np.isnan(result["avg_roe_5y"].iloc[0])

    def test_stateless_sentinel(self):
        assert hybrid_scoring._SANITIZE_IS_STATELESS is True


# ---------------------------------------------------------------------------
# _alias_factors
# ---------------------------------------------------------------------------

class TestAliasFactors:
    def test_snake_case_passthrough(self):
        inp = {f: float(i) for i, f in enumerate(FEATURES)}
        out = _alias_factors(inp)
        for feat in FEATURES:
            assert out[feat] == inp[feat]

    def test_title_case_mapping(self):
        inp = {"Score": 75.0, "PE_Ratio": 18.0, "ROCE%": 22.0}
        out = _alias_factors(inp)
        assert out["score"]    == 75.0
        assert out["pe_ratio"] == 18.0
        assert out["roce"]     == 22.0

    def test_missing_keys_default_to_nan(self):
        out = _alias_factors({})
        for feat in FEATURES:
            assert np.isnan(out[feat])


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestUtilityFunctions:
    def test_finite_or_none_finite(self):
        assert _finite_or_none(3.14) == pytest.approx(3.14)

    def test_finite_or_none_nan(self):
        assert _finite_or_none(float("nan")) is None

    def test_finite_or_none_inf(self):
        assert _finite_or_none(float("inf")) is None

    def test_finite_or_none_bad_type(self):
        assert _finite_or_none("hello") is None

    def test_spearman_ic_perfect(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0])
        assert _spearman_ic(s, s) == pytest.approx(1.0)

    def test_spearman_ic_too_few_obs(self):
        s = pd.Series([1.0])
        assert _spearman_ic(s, s) is None

    def test_top_quantile_sharpe_returns_float(self):
        returns = pd.Series([0.10, 0.05, -0.02, 0.08, 0.12])
        sharpe = _top_quantile_sharpe(returns)
        assert isinstance(sharpe, float) or sharpe is None


# ---------------------------------------------------------------------------
# walk_forward_validate — structural correctness
# ---------------------------------------------------------------------------

class TestWalkForwardValidate:
    def test_expanding_windows_train_sizes(self, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "_make_xgb_regressor", lambda: _ScoreEchoRegressor())
        metrics = walk_forward_validate(_make_wf_frame(), min_train_rows=4, min_train_periods=2)
        assert metrics["status"] == "OK"
        train_rows = [w["train_rows"] for w in metrics["windows"]]
        # Each fold should have strictly more training rows than the previous
        assert all(train_rows[i] < train_rows[i + 1] for i in range(len(train_rows) - 1))

    def test_correct_fold_count(self, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "_make_xgb_regressor", lambda: _ScoreEchoRegressor())
        metrics = walk_forward_validate(_make_wf_frame(n_quarters=6), min_train_rows=4, min_train_periods=2)
        assert metrics["status"] == "OK"
        assert metrics["folds"] == 4

    def test_perfect_signal_ic_near_one(self, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "_make_xgb_regressor", lambda: _ScoreEchoRegressor())
        metrics = walk_forward_validate(_make_wf_frame(), min_train_rows=4, min_train_periods=2)
        # With a near-perfect linear signal, IC should be close to 1
        assert metrics["spearman_ic"] == pytest.approx(1.0, abs=0.05)

    def test_skips_when_too_few_rows(self, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "_make_xgb_regressor", lambda: _ScoreEchoRegressor())
        metrics = walk_forward_validate(_make_wf_frame().head(3), min_train_rows=4, min_train_periods=2)
        assert metrics["status"] == "SKIPPED"
        assert "not enough" in metrics["reason"]

    def test_skips_when_missing_columns(self):
        df = _make_wf_frame().drop(columns=["forward_return"])
        metrics = walk_forward_validate(df)
        assert metrics["status"] == "SKIPPED"
        assert "missing columns" in metrics["reason"]

    def test_holdout_rows_excluded(self, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "_make_xgb_regressor", lambda: _ScoreEchoRegressor())
        # Inject a few rows inside the holdout period
        df = _make_wf_frame()
        holdout_rows = df.copy()
        holdout_rows["as_of_date"] = pd.to_datetime("2019-06-30")
        combined = pd.concat([df, holdout_rows], ignore_index=True)
        metrics = walk_forward_validate(combined, min_train_rows=4, min_train_periods=2)
        assert metrics["holdout_rows_excluded"] == len(holdout_rows)

    def test_per_fold_metrics_populated(self, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "_make_xgb_regressor", lambda: _ScoreEchoRegressor())
        metrics = walk_forward_validate(_make_wf_frame(), min_train_rows=4, min_train_periods=2)
        for w in metrics["windows"]:
            assert "fold_ic" in w
            assert "fold_hit_rate" in w

    def test_result_is_json_serialisable(self, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "_make_xgb_regressor", lambda: _ScoreEchoRegressor())
        metrics = walk_forward_validate(_make_wf_frame(), min_train_rows=4, min_train_periods=2)
        json_str = json.dumps(metrics)   # must not raise
        assert isinstance(json_str, str)


# ---------------------------------------------------------------------------
# predict_and_explain
# ---------------------------------------------------------------------------

class TestPredictAndExplain:
    def test_returns_fallback_when_no_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", str(tmp_path / "absent.pkl"))
        result = hybrid_scoring.predict_and_explain({"score": 75.0})
        assert result["ml_prediction"] is None
        assert result["shap_values"]   == {}

    def test_shap_values_sorted_by_absolute_value(self, tmp_path, monkeypatch):
        # Train a tiny real XGBoost on synthetic data, then run predict_and_explain
        import xgboost as xgb

        X = pd.DataFrame(np.random.rand(40, len(FEATURES)), columns=FEATURES)
        y = X["score"] * 0.5 + np.random.rand(40) * 0.1
        model = xgb.XGBRegressor(n_estimators=10, random_state=0)
        model.fit(X, y)

        model_path = str(tmp_path / "model.pkl")
        import joblib
        joblib.dump(model, model_path)
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", model_path)

        result = hybrid_scoring.predict_and_explain(dict.fromkeys(FEATURES, 0.5))
        shap_vals = list(result["shap_values"].values())
        assert shap_vals == sorted(shap_vals, key=abs, reverse=True)

    def test_top_drivers_direction_label(self, tmp_path, monkeypatch):
        import joblib
        import xgboost as xgb

        X = pd.DataFrame(np.random.rand(40, len(FEATURES)), columns=FEATURES)
        y = X["score"] + np.random.rand(40) * 0.01
        model = xgb.XGBRegressor(n_estimators=10, random_state=0)
        model.fit(X, y)
        model_path = str(tmp_path / "model.pkl")
        joblib.dump(model, model_path)
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", model_path)

        result = hybrid_scoring.predict_and_explain({"score": 80.0})
        for driver in result["top_drivers"]:
            assert driver["direction"] in ("bullish", "bearish")
            assert "feature" in driver
            assert "shap_value" in driver
            assert "feature_value" in driver

    def test_ml_prediction_is_percentage(self, tmp_path, monkeypatch):
        import joblib
        import xgboost as xgb

        X = pd.DataFrame(np.random.rand(40, len(FEATURES)), columns=FEATURES)
        y = pd.Series([0.05] * 40)
        model = xgb.XGBRegressor(n_estimators=5, random_state=0)
        model.fit(X, y)
        model_path = str(tmp_path / "model.pkl")
        joblib.dump(model, model_path)
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", model_path)

        result = hybrid_scoring.predict_and_explain({"score": 50.0})
        # ml_prediction should be the raw prediction × 100 (in %)
        assert result["ml_prediction"] == pytest.approx(5.0, abs=0.5)


# ---------------------------------------------------------------------------
# batch_predict
# ---------------------------------------------------------------------------

class TestBatchPredict:
    def test_returns_same_length(self, tmp_path, monkeypatch):
        import joblib
        import xgboost as xgb

        X = pd.DataFrame(np.random.rand(30, len(FEATURES)), columns=FEATURES)
        y = np.random.rand(30)
        model = xgb.XGBRegressor(n_estimators=5, random_state=0)
        model.fit(X, y)
        model_path = str(tmp_path / "model.pkl")
        joblib.dump(model, model_path)
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", model_path)

        stocks = [{"symbol": f"S{i}", "score": float(i * 5)} for i in range(10)]
        results = hybrid_scoring.batch_predict(stocks)
        assert len(results) == 10

    def test_fallback_when_no_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", str(tmp_path / "absent.pkl"))
        stocks = [{"symbol": "X", "score": 50.0}]
        results = hybrid_scoring.batch_predict(stocks)
        assert results[0]["ml_prediction"] is None


# ---------------------------------------------------------------------------
# Feature leakage audit
# ---------------------------------------------------------------------------

class TestFeatureLeakageAudit:
    def test_safe_feature_returns_safe(self):
        from modules.feature_leakage_audit import audit_features

        n = 30
        df = pd.DataFrame(
            {feat: np.random.rand(n) for feat in FEATURES} | {"forward_return": np.random.rand(n)}
        )
        report = audit_features(df)
        assert isinstance(report.leaking_count, int)
        assert isinstance(report.review_count,   int)

    def test_high_correlation_momentum_feature_flagged(self):
        from modules.feature_leakage_audit import audit_features

        n = 50
        y = np.linspace(0, 1, n)
        df = pd.DataFrame(
            {feat: np.zeros(n) for feat in FEATURES} | {"forward_return": y}
        )
        # Make ret_6m perfectly correlated with forward_return
        df["ret_6m"] = y
        report = audit_features(df)
        verdicts = {v.feature: v for v in report.verdicts}
        assert verdicts["ret_6m"].classification in ("LEAKING", "NEEDS_REVIEW")

    def test_vif_computation(self):
        from modules.feature_leakage_audit import compute_vif

        n = 50
        df = pd.DataFrame({feat: np.random.rand(n) for feat in FEATURES})
        vif_results = compute_vif(df)
        assert len(vif_results) == len(FEATURES)
        for row in vif_results:
            assert "feature" in row
            assert "vif"     in row
            assert "flag"    in row


# ---------------------------------------------------------------------------
# Holdout module
# ---------------------------------------------------------------------------

class TestHoldout:
    def test_split_holdout_date_range(self):
        from modules.holdout import split_holdout

        dates = pd.date_range("2017-01-01", "2022-12-31", freq="QS")
        df = pd.DataFrame({"as_of_date": dates, "val": range(len(dates))})
        train, holdout = split_holdout(df)

        holdout_dates = pd.to_datetime(holdout["as_of_date"])
        train_dates   = pd.to_datetime(train["as_of_date"])
        assert holdout_dates.between(HOLDOUT_START, HOLDOUT_END).all()
        assert not train_dates.between(HOLDOUT_START, HOLDOUT_END).any()
        assert len(train) + len(holdout) == len(df)

    def test_evaluate_holdout_metrics(self):
        from modules.holdout import evaluate_holdout

        class _ConstModel:
            def predict(self, X):
                return np.full(len(X), 0.05)

        n = 20
        df = pd.DataFrame(
            {feat: np.random.rand(n) for feat in FEATURES}
            | {"forward_return": np.random.rand(n)}
        )
        result = evaluate_holdout(_ConstModel(), df)
        assert result["status"] == "OK"
        assert "oos_r2"      in result
        assert "spearman_ic" in result
        assert "hit_rate"    in result

    def test_compare_performance_flags_overfitting(self):
        from modules.holdout import compare_performance

        result = compare_performance(0.50, 0.10, threshold=0.30)
        assert result["overfitting_detected"] is True
        assert result["ic_gap"] == pytest.approx(0.40, abs=1e-6)

    def test_compare_performance_no_overfitting(self):
        from modules.holdout import compare_performance

        result = compare_performance(0.30, 0.25, threshold=0.30)
        assert result["overfitting_detected"] is False


# ---------------------------------------------------------------------------
# IC monitor
# ---------------------------------------------------------------------------

class TestICMonitor:
    def test_compute_ic_by_regime_keys(self):
        from modules.ic_monitor import compute_ic_by_regime

        n = 30
        df = pd.DataFrame({
            "prediction":    np.random.rand(n),
            "forward_return": np.random.rand(n),
        })
        regime = pd.Series(["BULL"] * 15 + ["BEAR"] * 15, index=df.index)
        result = compute_ic_by_regime(df, regime)
        assert "BULL" in result
        assert "BEAR" in result
        for v in result.values():
            assert "ic"         in v
            assert "n_obs"      in v
            assert "confidence" in v

    def test_rolling_ic_returns_dataframe(self):
        from modules.ic_monitor import compute_rolling_ic

        n = 40
        dates = pd.date_range("2022-01-01", periods=n, freq="ME")
        df = pd.DataFrame({
            "as_of_date":     dates,
            "prediction":     np.random.rand(n),
            "forward_return":  np.random.rand(n),
        })
        rolling = compute_rolling_ic(df)
        assert isinstance(rolling, pd.DataFrame)
        assert "ic" in rolling.columns

    def test_detect_ic_drift_flags(self):
        from modules.ic_monitor import detect_ic_drift

        df = pd.DataFrame({"ic": [0.20, 0.18, 0.17, 0.16, 0.05, 0.04, 0.03, 0.02]})
        result = detect_ic_drift(df, lookback_periods=3, drift_threshold=0.08)
        assert result["drift_detected"] is True

    def test_detect_ic_drift_stable(self):
        from modules.ic_monitor import detect_ic_drift

        df = pd.DataFrame({"ic": [0.15, 0.14, 0.16, 0.15, 0.14, 0.16, 0.15, 0.15]})
        result = detect_ic_drift(df, lookback_periods=3, drift_threshold=0.08)
        assert result["drift_detected"] is False


# ---------------------------------------------------------------------------
# get_feature_importance
# ---------------------------------------------------------------------------

class TestGetFeatureImportance:
    def test_returns_empty_when_no_model(self, tmp_path, monkeypatch):
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", str(tmp_path / "absent.pkl"))
        imp = hybrid_scoring.get_feature_importance()
        assert imp == {}

    def test_returns_all_features(self, tmp_path, monkeypatch):
        import joblib
        import xgboost as xgb

        X = pd.DataFrame(np.random.rand(30, len(FEATURES)), columns=FEATURES)
        y = np.random.rand(30)
        model = xgb.XGBRegressor(n_estimators=10, random_state=0)
        model.fit(X, y)
        model_path = str(tmp_path / "model.pkl")
        joblib.dump(model, model_path)
        monkeypatch.setattr(hybrid_scoring, "MODEL_PATH", model_path)

        imp = hybrid_scoring.get_feature_importance()
        for feat in FEATURES:
            assert feat in imp
        total = sum(imp.values())
        assert total == pytest.approx(1.0, abs=0.01)
