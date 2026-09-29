from __future__ import annotations

import json
import ast
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from modules.scoring import ml_score

pytestmark = pytest.mark.ml


class _FrameResult:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def to_pandas(self) -> pd.DataFrame:
        return self._frame.copy()


class _LakeQuery:
    def select(self, *_args):
        return self

    def unique(self):
        return self

    def collect(self) -> pd.DataFrame:
        return pd.DataFrame({"symbol": ["AAA"]})


class _FeatureStore:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.lake = type("Lake", (), {"query_all": lambda _self, _name: _LakeQuery()})()
        self._frame = frame

    def generate_training_dataset(self, *_args) -> _FrameResult:
        return _FrameResult(self._frame)


class _Model:
    def fit(self, *_args, **_kwargs):
        return self


class _Explainer:
    expected_value = 0.125

    def __init__(self, _model) -> None:
        pass


def _training_frame(rows: int = 24) -> pd.DataFrame:
    frame = pd.DataFrame(
        np.zeros((rows, len(ml_score.FEATURES))),
        columns=ml_score.FEATURES,
    )
    frame["forward_return"] = np.linspace(-0.1, 0.2, rows)
    return frame


def test_train_hybrid_model_saves_walk_forward_report(monkeypatch, tmp_path):
    frame = _training_frame()
    reports: list[dict] = []

    monkeypatch.setattr(ml_score, "FeatureStore", lambda: _FeatureStore(frame))
    monkeypatch.setattr(ml_score, "_build_training_frame", lambda _raw: frame)
    monkeypatch.setattr("modules.holdout.split_holdout", lambda data: (data, pd.DataFrame()))
    monkeypatch.setattr(
        ml_score,
        "walk_forward_validate",
        lambda _data: {"status": "SKIPPED", "reason": "test"},
    )
    monkeypatch.setattr(ml_score, "_save_walk_forward_report", reports.append)
    monkeypatch.setattr(ml_score, "_make_xgb_regressor", _Model)
    monkeypatch.setattr(ml_score, "check_shap_dominance", lambda *_a, **_k: (True, "OK", {}))
    monkeypatch.setattr(ml_score, "_get_shap", lambda: type("FakeShap", (), {"TreeExplainer": _Explainer}))
    monkeypatch.setattr(ml_score.joblib, "dump", lambda *_a, **_k: None)
    monkeypatch.setattr(ml_score, "MODEL_PATH", str(tmp_path / "model.pkl"))
    monkeypatch.setattr(ml_score, "CLASSIFIER_PATH", str(tmp_path / "classifier.pkl"))
    monkeypatch.setattr(ml_score, "SHAP_CACHE_PATH", str(tmp_path / "shap.json"))

    assert ml_score.train_hybrid_model() is True
    assert reports == [{
        "status": "SKIPPED",
        "reason": "test",
        "shap_dominance": {
            "checked": True,
            "passes_threshold": True,
            "top_feature": None,
            "top_feature_share": None,
            "threshold": ml_score.SHAP_DOMINANCE_THRESHOLD,
        },
    }]


def test_bootstrap_writes_shap_cache(monkeypatch, tmp_path):
    frame = _training_frame()
    frame["symbol"] = [f"S{i}" for i in range(len(frame))]

    monkeypatch.setattr(
        "modules.data_layer.db_utils.get_db_connection",
        lambda _name: nullcontext(object()),
    )
    monkeypatch.setattr(ml_score.pd, "read_sql", lambda *_a, **_k: frame.copy())
    monkeypatch.setattr(ml_score, "compute_features_batch", lambda data: data)
    monkeypatch.setattr(ml_score, "_make_xgb_regressor", _Model)
    monkeypatch.setattr(ml_score, "check_shap_dominance", lambda *_a, **_k: (True, "OK", {}))
    monkeypatch.setattr(ml_score, "_get_shap", lambda: type("FakeShap", (), {"TreeExplainer": _Explainer}))
    monkeypatch.setattr(ml_score.joblib, "dump", lambda *_a, **_k: None)
    monkeypatch.setattr(ml_score, "_save_walk_forward_report", lambda _report: None)
    monkeypatch.setattr(ml_score, "MODEL_PATH", str(tmp_path / "model.pkl"))
    monkeypatch.setattr(ml_score, "SHAP_CACHE_PATH", str(tmp_path / "shap.json"))

    assert ml_score.bootstrap_synthetic_model() is True
    assert json.loads((tmp_path / "shap.json").read_text()) == {
        "expected_value": 0.125,
        "bootstrap": True,
    }


def test_ml_safe_float_preserves_default_and_rejects_non_finite_values():
    assert ml_score.safe_float("[12.5]", default=-1.0) == 12.5
    assert ml_score.safe_float(float("nan"), default=7.0) == 7.0


def test_optional_ml_packages_are_not_imported_at_module_scope():
    tree = ast.parse(Path(ml_score.__file__).read_text(encoding="utf-8"))
    eager = {
        alias.name.split(".")[0]
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (node.names if isinstance(node, ast.Import) else [ast.alias(node.module or "")])
    }
    assert eager.isdisjoint({"shap", "xgboost", "optuna"})
