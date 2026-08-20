"""
XGBoost ML scoring: model creation, training, prediction, SHAP explainability.

Extracted from modules/hybrid_scoring.py.
Contains the two-model architecture (Classifier + Regressor) and SHAP integration.
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass
from typing import Any

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import shap
from shap.explainers import _tree

# --- Monkey-patch for SHAP XGBoost Tree Loader ---
_original_decode = getattr(_tree, "decode_ubjson_buffer", None)
if _original_decode:
    def _patched_decode(fd):
        jmodel = _original_decode(fd)
        try:
            bs = jmodel.get("learner", {}).get("learner_model_param", {}).get("base_score")
            if isinstance(bs, str) and bs.startswith("["):
                match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", bs)
                if match:
                    jmodel["learner"]["learner_model_param"]["base_score"] = match.group(0)
        except Exception:
            pass
        return jmodel
    _tree.decode_ubjson_buffer = _patched_decode

from modules.feature_factory import (
    EXTENDED_FEATURE_BOUNDS,
    EXTENDED_FEATURES,
    compute_all_features,
    sanitize_features as _sanitize_extended,
)
from modules.scoring.utils import safe_float, _finite_or_none

warnings.filterwarnings("ignore")

try:
    from core.observability.logger import get_logger
    _log = get_logger("modules.scoring.ml_score")
except Exception:
    import logging
    _log = logging.getLogger("modules.scoring.ml_score")

# --- Paths & Constants ---

MODEL_PATH = os.path.join("runtime", "models", "xgboost_meta_model.pkl")
CLASSIFIER_PATH = os.path.join("runtime", "models", "xgboost_classifier.pkl")
SHAP_CACHE_PATH = os.path.join("runtime", "models", "shap_expected_value.json")

FEATURES: list[str] = EXTENDED_FEATURES
FEATURE_BOUNDS: dict[str, tuple[float, float]] = EXTENDED_FEATURE_BOUNDS

CLASSIFIER_WEIGHT = 0.6
REGRESSOR_WEIGHT = 0.4

_XGB_PARAMS: dict[str, Any] = {
    "n_estimators": 100,
    "learning_rate": 0.05,
    "max_depth": 4,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 3,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "eval_metric": "rmse",
}

SHAP_DOMINANCE_THRESHOLD = 0.90

_SANITIZE_IS_STATELESS = True


# --- Feature helpers ---

def _sanitize_features(df: pd.DataFrame) -> pd.DataFrame:
    assert _SANITIZE_IS_STATELESS
    return _sanitize_extended(df)


def _alias_factors(factors_dict: dict) -> dict:
    """Map legacy factor names to FEATURES snake_case keys."""
    mapped = {
        "score": factors_dict.get("score", factors_dict.get("Score", np.nan)),
        "sales_cagr_5y": factors_dict.get("sales_cagr_5y", factors_dict.get("Sales_Growth_5Y%", np.nan)),
        "avg_roe_5y": factors_dict.get("avg_roe_5y", factors_dict.get("Avg_ROE_5Y%", np.nan)),
        "pe_ratio": factors_dict.get("pe_ratio", factors_dict.get("PE_Ratio", np.nan)),
        "debt_equity": factors_dict.get("debt_equity", factors_dict.get("Debt_Equity", np.nan)),
        "cfo_pat_ratio": factors_dict.get("cfo_pat_ratio", factors_dict.get("CFO_PAT_Ratio", np.nan)),
        "market_cap_cr": factors_dict.get("market_cap_cr", factors_dict.get("Market_Cap_Cr", np.nan)),
        "ret_1m": factors_dict.get("ret_1m", factors_dict.get("Ret_1M", np.nan)),
        "ret_3m": factors_dict.get("ret_3m", factors_dict.get("Ret_3M", np.nan)),
        "ret_6m": factors_dict.get("ret_6m", factors_dict.get("Ret_6M", np.nan)),
        "vol_breakout": factors_dict.get("vol_breakout", factors_dict.get("Vol_Breakout", np.nan)),
        "dist_from_52w_high": factors_dict.get("dist_from_52w_high", factors_dict.get("Dist_From_52W_High", np.nan)),
        "roce": factors_dict.get("roce", factors_dict.get("ROCE%", np.nan)),
    }

    symbol = factors_dict.get("symbol", factors_dict.get("Symbol", ""))
    if symbol:
        extended = compute_all_features(str(symbol), factors_dict)
        for feat in FEATURES:
            if feat not in mapped:
                mapped[feat] = extended.get(feat, np.nan)
    else:
        for feat in FEATURES:
            if feat not in mapped:
                mapped[feat] = factors_dict.get(feat, np.nan)

    return mapped


# --- Model factory ---

def _make_xgb_regressor(**overrides) -> xgb.XGBRegressor:
    params = {**_XGB_PARAMS, **overrides}
    params.pop("eval_metric", None)
    return xgb.XGBRegressor(**params)


def _make_xgb_classifier(**overrides) -> xgb.XGBClassifier:
    params = {**_XGB_PARAMS, **overrides}
    params["eval_metric"] = "logloss"
    params["objective"] = "binary:logistic"
    return xgb.XGBClassifier(**params)


# --- SHAP dominance check ---

def check_shap_dominance(model, X: pd.DataFrame, threshold: float = SHAP_DOMINANCE_THRESHOLD) -> dict:
    """Reject model if any single feature dominates SHAP importance."""
    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
        abs_mean = np.abs(shap_values).mean(axis=0)
        total = abs_mean.sum()
        if total == 0:
            return {"dominant": False, "max_share": 0.0}
        shares = abs_mean / total
        max_idx = int(np.argmax(shares))
        max_share = float(shares[max_idx])
        return {
            "dominant": max_share > threshold,
            "max_share": round(max_share, 4),
            "max_feature": X.columns[max_idx] if max_idx < len(X.columns) else "unknown",
        }
    except Exception as e:
        _log.warning("SHAP dominance check failed", error=str(e))
        return {"dominant": False, "max_share": 0.0, "error": str(e)}


# --- Public API ---

def model_is_trained() -> bool:
    return os.path.exists(MODEL_PATH)


def get_feature_importance() -> dict:
    """Return feature importance from the trained regressor model."""
    if not os.path.exists(MODEL_PATH):
        return {}
    try:
        model = joblib.load(MODEL_PATH)
        importance = model.feature_importances_
        return dict(zip(FEATURES, [round(float(v), 4) for v in importance]))
    except Exception:
        return {}


@dataclass
class PredictionResult:
    score: float
    factors: dict
    shap_values: dict
    confidence: float
    classifier_prob: float | None = None
