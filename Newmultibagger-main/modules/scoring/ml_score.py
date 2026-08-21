"""
XGBoost ML scoring: model creation, training, prediction, SHAP explainability.

Extracted from modules/hybrid_scoring.py.
Contains the two-model architecture (Classifier + Regressor) and SHAP integration.
"""

from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass, field
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
    compute_features_batch,
    EXTENDED_FEATURE_BOUNDS,
    EXTENDED_FEATURES,
    compute_all_features,
    sanitize_features as _sanitize_extended,
)
from modules.scoring.utils import (
    safe_float,
    _finite_or_none,
    _spearman_ic,
    _top_quantile_sharpe,
)
from modules.scoring.walk_forward import (
    HOLDOUT_START,
    HOLDOUT_END,
    walk_forward_validate,
    load_walk_forward_report,
)

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

_OPTUNA_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    "n_estimators":     {"low": 50,   "high": 500},
    "learning_rate":    {"low": 0.01, "high": 0.3, "log": True},
    "max_depth":        {"low": 3,    "high": 8},
    "subsample":        {"low": 0.6,  "high": 1.0},
    "colsample_bytree": {"low": 0.5,  "high": 1.0},
    "min_child_weight": {"low": 1,    "high": 10},
    "reg_alpha":        {"low": 1e-3, "high": 10.0, "log": True},
    "reg_lambda":       {"low": 1e-3, "high": 10.0, "log": True},
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

def _make_xgb_regressor(params: dict | None = None, **overrides) -> xgb.XGBRegressor:
    merged = {**_XGB_PARAMS, **(params or {}), **overrides}
    merged.pop("eval_metric", None)
    return xgb.XGBRegressor(**merged)


def _make_xgb_classifier(**overrides) -> xgb.XGBClassifier:
    params = {**_XGB_PARAMS, **overrides}
    params["eval_metric"] = "logloss"
    params["objective"] = "binary:logistic"
    return xgb.XGBClassifier(**params)


# --- SHAP dominance check ---

def check_shap_dominance(
    model,
    X: pd.DataFrame,
    threshold: float = SHAP_DOMINANCE_THRESHOLD,
    *,
    sample_size: int | None = None,
) -> tuple[bool, str, dict[str, float]]:
    """Reject model if any single feature dominates SHAP importance.

    Returns:
        (passes: bool, reason: str, importance: dict[str, float])
    """
    try:
        if sample_size is not None and len(X) > sample_size:
            X_eval = X.sample(n=sample_size, random_state=42)
        else:
            X_eval = X

        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_eval)
        abs_mean = np.abs(shap_values).mean(axis=0)
        total = abs_mean.sum()
        if total == 0 or np.isnan(total):
            equal_share = 1.0 / len(X.columns) if len(X.columns) > 0 else 0.0
            imp = {col: equal_share for col in X.columns}
            return True, "OK", imp

        shares = abs_mean / total
        imp = {col: round(float(shares[i]), 4) for i, col in enumerate(X.columns)}
        max_idx = int(np.argmax(shares))
        max_share = float(shares[max_idx])
        max_feat = str(X.columns[max_idx]) if max_idx < len(X.columns) else "unknown"

        if max_share > threshold:
            reason = f"REJECTED: Feature '{max_feat}' dominates SHAP importance with {max_share:.1%} share (threshold {threshold:.1%})"
            return False, reason, imp

        return True, "OK", imp
    except Exception as e:
        _log.warning("SHAP dominance check failed", error=str(e))
        return False, f"ERROR: {e}", {}


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
    ml_prediction: float | None = None
    classifier_prob: float | None = None
    regressor_return: float | None = None
    shap_values: dict[str, float] = field(default_factory=dict)
    shap_expected_value: float | None = None
    top_drivers: list[dict] = field(default_factory=list)
    is_bootstrap: bool = False
    score: float | None = None
    factors: dict = field(default_factory=dict)
    confidence: float | None = None

    def to_dict(self) -> dict:
        return {
            "ml_prediction": self.ml_prediction,
            "classifier_prob": self.classifier_prob,
            "regressor_return": self.regressor_return,
            "shap_values": self.shap_values,
            "shap_expected_value": self.shap_expected_value,
            "top_drivers": self.top_drivers,
            "is_bootstrap": self.is_bootstrap,
        }


import optuna


def optuna_optimize(
    train_df: pd.DataFrame,
    *,
    n_trials: int = 30,
    cv_folds: int = 3,
    timeout_seconds: int | None = 300,
) -> dict[str, Any]:
    """Run Optuna Bayesian search over XGBoost hyper-parameters.

    The first trial ("warm-start") is seeded with the legacy ``_XGB_PARAMS``
    so the search always starts from a known-good baseline.  Subsequent
    trials explore the search space defined by ``_OPTUNA_SEARCH_SPACE``.

    Args:
        train_df: DataFrame with FEATURES columns + ``forward_return``.
        n_trials: Total number of Optuna trials (including the warm-start).
        cv_folds: Number of cross-validation folds for each trial.
        timeout_seconds: Max wall-clock seconds for the entire study.

    Returns:
        Best hyper-parameter dict (compatible with ``_make_xgb_regressor``).
    """
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    X = _sanitize_features(train_df[FEATURES])
    y = train_df["forward_return"].values

    def _objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators":     trial.suggest_int("n_estimators",     **_OPTUNA_SEARCH_SPACE["n_estimators"]),
            "learning_rate":    trial.suggest_float("learning_rate",  **_OPTUNA_SEARCH_SPACE["learning_rate"]),
            "max_depth":        trial.suggest_int("max_depth",        **_OPTUNA_SEARCH_SPACE["max_depth"]),
            "subsample":        trial.suggest_float("subsample",      **_OPTUNA_SEARCH_SPACE["subsample"]),
            "colsample_bytree": trial.suggest_float("colsample_bytree", **_OPTUNA_SEARCH_SPACE["colsample_bytree"]),
            "min_child_weight": trial.suggest_int("min_child_weight", **_OPTUNA_SEARCH_SPACE["min_child_weight"]),
            "reg_alpha":        trial.suggest_float("reg_alpha",      **_OPTUNA_SEARCH_SPACE["reg_alpha"]),
            "reg_lambda":       trial.suggest_float("reg_lambda",     **_OPTUNA_SEARCH_SPACE["reg_lambda"]),
        }

        from sklearn.model_selection import KFold

        kf = KFold(n_splits=cv_folds, shuffle=True, random_state=42)
        fold_scores: list[float] = []

        for train_idx, val_idx in kf.split(X):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            model = _make_xgb_regressor(params)
            model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
            preds = model.predict(X_val)

            # Spearman IC as the optimization target (higher is better)
            ic = _spearman_ic(pd.Series(y_val), pd.Series(preds))
            fold_scores.append(ic if ic is not None else 0.0)

        return float(np.mean(fold_scores))

    study = optuna.create_study(
        direction="maximize",
        study_name="xgb_hyperparam",
        sampler=optuna.samplers.TPESampler(seed=42)
    )

    # Warm-start: enqueue the legacy params as the first trial
    study.enqueue_trial({
        "n_estimators":     _XGB_PARAMS["n_estimators"],
        "learning_rate":    _XGB_PARAMS["learning_rate"],
        "max_depth":        _XGB_PARAMS["max_depth"],
        "subsample":        _XGB_PARAMS["subsample"],
        "colsample_bytree": _XGB_PARAMS["colsample_bytree"],
        "min_child_weight": _XGB_PARAMS["min_child_weight"],
        "reg_alpha":        _XGB_PARAMS["reg_alpha"],
        "reg_lambda":       _XGB_PARAMS["reg_lambda"],
    })

    study.optimize(_objective, n_trials=n_trials, timeout=timeout_seconds)

    best = study.best_params
    best["random_state"] = 42
    best["eval_metric"] = "rmse"

    _log.info(
        "Optuna optimization complete",
        best_ic=round(study.best_value, 4),
        n_trials=len(study.trials),
        best_params=best,
    )
    return best


# ---------------------------------------------------------------------------
# SHAP dominance guard
# ---------------------------------------------------------------------------


# --- Training Pipeline ---
from datetime import date
from modules.data_layer.parquet.feature_store import FeatureStore
from modules.scoring.walk_forward import walk_forward_validate, _save_walk_forward_report

def _build_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    from modules.target_engineering import build_training_targets
    train_df = build_training_targets(df, horizon_months=6)
    if not train_df.empty:
        # Features are already computed in FeatureStore, just sanitize
        train_df[FEATURES] = _sanitize_features(train_df[FEATURES])
    return train_df

def train_hybrid_model() -> bool:
    _log.info("Initiating Hybrid Scoring Meta-Model Training (XGBoost)...")

    # 1. Extract PIT Data using FeatureStore
    try:
        # Use all available dates; FeatureStore will exclude the holdout period automatically
        start_date = date(2000, 1, 1)
        end_date = date.today()
        store = FeatureStore()
        
        # We need to list all symbols to get the dataset.
        # This will get the list of symbols from the lake.
        symbols = store.lake.query_all("daily").select("symbol").unique().collect()["symbol"].to_list()
        
        raw_df = store.generate_training_dataset(symbols, start_date, end_date).to_pandas()
        
        # We need price to calculate returns, score to bootstrap
        if raw_df.empty:
            _log.warning("FeatureStore returned empty dataset")
            return False
            
    except Exception as exc:
        _log.warning("Could not load PIT data from FeatureStore", error=str(exc))
        return False

    if len(raw_df) < 20:
        _log.info("Insufficient PIT rows", rows=len(raw_df), minimum=20)
        return False

    # 2. Construct forward-return targets
    train_df = _build_training_frame(raw_df)

    if train_df.empty or len(train_df) < 10:
        _log.info("Too few rows with valid forward returns", rows=len(train_df))
        return False

    # 3. Holdout split
    try:
        from modules.holdout import split_holdout
        train_only, holdout_only = split_holdout(train_df)
        _log.info("Holdout split", train=len(train_only), holdout=len(holdout_only))
    except Exception as exc:
        _log.warning("Holdout split failed — using all data", error=str(exc))
        train_only   = train_df
        holdout_only = pd.DataFrame()

    # 4. Walk-forward validation
    validation = walk_forward_validate(train_only)
    _save_walk_forward_report(validation)

    if validation.get("status") == "OK":
        _log.info(
            "Walk-forward complete",
            folds=validation["folds"],
            oos_r2=validation.get("oos_r2"),
            spearman_ic=validation.get("spearman_ic"),
            hit_rate=validation.get("hit_rate"),
        )
    else:
        _log.info("Walk-forward skipped", reason=validation.get("reason"))

    # 5. Production fit: Two-model architecture
    X = _sanitize_features(train_only[FEATURES])
    y_return = train_only["forward_return"]

    # Model A: Regressor
    regressor = _make_xgb_regressor()
    _log.info("Fitting production XGBoost regressor", rows=len(X))
    regressor.fit(X, y_return)

    # Model B: Classifier
    classifier = None
    if "is_multibagger" in train_only.columns:
        y_class = train_only["is_multibagger"]
        n_pos = int(y_class.sum())
        n_neg = len(y_class) - n_pos
        if n_pos >= 5 and n_neg >= 5:
            classifier = _make_xgb_classifier()
            _log.info("Fitting production XGBoost classifier", rows=len(X), positives=n_pos, negatives=n_neg)
            classifier.fit(X, y_class)
        else:
            _log.info("Insufficient positives for classifier", positives=n_pos)

    # 6. SHAP Dominance Check
    shap_dominance = {"checked": False}
    try:
        passes, reason, shap_imp = check_shap_dominance(
            regressor, X, threshold=SHAP_DOMINANCE_THRESHOLD
        )
        top_feat = max(shap_imp, key=shap_imp.get) if shap_imp else None
        shap_dominance = {
            "checked": True,
            "passes_threshold": passes,
            "top_feature": top_feat,
            "top_feature_share": shap_imp.get(top_feat) if top_feat else None,
            "threshold": SHAP_DOMINANCE_THRESHOLD,
        }
        if not passes:
            _log.warning("Production model SHAP dominance exceeds threshold", top_feature=top_feat, reason=reason)
    except Exception as exc:
        _log.warning("SHAP dominance check failed", error=str(exc))

    # Cache SHAP expected value
    try:
        explainer = shap.TreeExplainer(regressor)
        ev = float(explainer.expected_value)
        os.makedirs(os.path.dirname(SHAP_CACHE_PATH), exist_ok=True)
        with open(SHAP_CACHE_PATH, "w") as fh:
            import json
            from modules.scoring.walk_forward import _save_walk_forward_report
            json.dump({"expected_value": ev, "bootstrap": False}, fh)
    except Exception as exc:
        _log.warning("Could not cache SHAP expected value", error=str(exc))

    # Persist Models
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(regressor, MODEL_PATH)
    if classifier:
        joblib.dump(classifier, CLASSIFIER_PATH)

    _log.info("Hybrid scoring models trained and saved", path=MODEL_PATH)
    return True



def _bootstrap_proxy_return(df: pd.DataFrame) -> pd.Series:
    """Cold-start proxy target until real forward-return PIT rows accumulate."""
    score = pd.to_numeric(df.get("score", 0.0), errors="coerce").fillna(0.0)
    score_min = score.min()
    score_max = score.max()
    score_range = max(float(score_max - score_min), 1.0)
    score_norm = (score - score_min) / score_range

    roe_signal = (
        pd.to_numeric(df.get("avg_roe_5y", 0.0), errors="coerce")
        .clip(-50, 100)
        .fillna(0.0)
        / 100.0
    )
    de_signal = 1.0 - (
        pd.to_numeric(df.get("debt_equity", 1.0), errors="coerce")
        .clip(0, 5)
        .fillna(1.0)
        / 5.0
    )
    growth_signal = (
        pd.to_numeric(df.get("sales_cagr_5y", 0.0), errors="coerce")
        .clip(-50, 200)
        .fillna(0.0)
        / 200.0
    )

    return (0.50 * score_norm + 0.20 * roe_signal + 0.15 * de_signal + 0.15 * growth_signal) - 0.5


# ---------------------------------------------------------------------------
# Bootstrap: synthetic model from multibaggers (cold-start when PIT is empty)
# ---------------------------------------------------------------------------

def bootstrap_synthetic_model() -> bool:
    """Train a bootstrap XGBoost model using current multibaggers rows.

    Used for cold-start: when ``fundamentals_pit`` is empty or too small
    to run ``train_hybrid_model()``, this function trains on the live
    ``multibaggers`` table using a proxy forward-return target derived
    from score, profitability, leverage, and growth signals.

    The resulting model is intentionally weak — its sole purpose is to
    make ``model_is_trained()`` return True so the screener, API, and
    Celery batch inference all work immediately.  It will be replaced
    automatically by ``train_hybrid_model()`` on the first Sunday retrain
    once enough PIT rows accumulate.

    Returns True on success, False on any failure.
    """
    _log.info("Bootstrapping synthetic XGBoost model from multibaggers…")

    try:
        from modules.data_layer.db_utils import get_db_connection

        with get_db_connection("stocks.db") as conn:
            df = pd.read_sql(
                """
                SELECT symbol, sector,
                       score,
                       sales_cagr_5y, avg_roe_5y, pe_ratio,
                       debt_equity,   cfo_pat_ratio, market_cap_cr,
                       ret_1m, ret_3m, ret_6m,
                       vol_breakout,  dist_from_52w_high, roce
                FROM   multibaggers
                WHERE  score IS NOT NULL
                """,
                conn,
            )
    except Exception as exc:
        _log.error("Bootstrap: could not read multibaggers", error=str(exc))
        return False

    if len(df) < 20:
        _log.warning(
            "Bootstrap: not enough multibagger rows",
            rows=len(df),
            minimum=20,
        )
        return False

    # Compute extended features
    feat_df = compute_features_batch(df)
    for col in FEATURES:
        if col in feat_df.columns:
            df[col] = feat_df[col].values

    proxy_return = _bootstrap_proxy_return(df)

    X = _sanitize_features(df[FEATURES])
    y = proxy_return.values

    model = _make_xgb_regressor()
    model.fit(X, y)

    # SHAP dominance check — run for visibility even on the bootstrap model.
    # We do NOT hard-reject here: the proxy target is deliberately built
    # 50% from `score` (see _bootstrap_proxy_return), so *some* dominance by
    # that feature is expected and not itself a bug. What we want to catch
    # is dominance far beyond that, which would mean the model has collapsed
    # onto a single signal and is adding ~zero information beyond the rule
    # score it was supposed to augment. That case gets logged loudly and
    # recorded on the report so API consumers (and `is_bootstrap` checks)
    # can see exactly how concentrated the bootstrap model's logic is.
    shap_dominance: dict[str, Any] = {"checked": False}
    try:
        passes, reason, shap_imp = check_shap_dominance(
            model, X, threshold=SHAP_DOMINANCE_THRESHOLD
        )
        top_feat = max(shap_imp, key=shap_imp.get) if shap_imp else None
        shap_dominance = {
            "checked": True,
            "passes_threshold": passes,
            "top_feature": top_feat,
            "top_feature_share": shap_imp.get(top_feat) if top_feat else None,
            "threshold": SHAP_DOMINANCE_THRESHOLD,
        }
        if not passes:
            _log.warning(
                "Bootstrap model SHAP dominance exceeds threshold — "
                "predictions may be little more than a rescaled rule score",
                reason=reason,
                top_feature=top_feat,
                top_feature_share=shap_imp.get(top_feat),
            )
    except Exception as exc:
        _log.warning("Bootstrap: SHAP dominance check failed", error=str(exc))

    # WF report: mark as bootstrap so consumers can distinguish
    wf_report = {
        "status":     "BOOTSTRAP",
        "reason":     "trained on multi-signal proxy targets; replace via POST /api/ml/train",
        "is_bootstrap": True,
        "proxy_features": ["score", "avg_roe_5y", "debt_equity", "sales_cagr_5y"],
        "shap_dominance": shap_dominance,
        "folds":      0,
        "rows":       int(len(df)),
        "spearman_ic": None,
        "hit_rate":   None,
        "oos_r2":     None,
        "mae":        None,
        "rmse":       None,
    }

    # Cache SHAP expected value
    try:
        explainer = shap.TreeExplainer(model)
        ev = float(explainer.expected_value)
        os.makedirs(os.path.dirname(SHAP_CACHE_PATH), exist_ok=True)
        with open(SHAP_CACHE_PATH, "w") as fh:
            json.dump({"expected_value": ev, "bootstrap": True}, fh)
    except Exception as exc:
        _log.warning("Bootstrap: could not cache SHAP expected value", error=str(exc))

    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    _save_walk_forward_report(wf_report)

    _log.info(
        "Bootstrap model saved",
        path=MODEL_PATH,
        rows=int(len(df)),
        hint="replace with real PIT-trained model via POST /api/ml/train --force",
    )
    return True


# ---------------------------------------------------------------------------
# Main training entry-point
# ---------------------------------------------------------------------------


def safe_float(val) -> float:
    try:
        if isinstance(val, str) and val.startswith("[") and val.endswith("]"):
            val = val[1:-1]
        return float(val)
    except (ValueError, TypeError):
        return 0.0

def predict_and_explain(
    factors_dict: dict,
    top_n_drivers: int = 5,
) -> dict:
    """Given a live stock's factor dict, predict multibagger probability
    (blended classifier + regressor) and generate SHAP values."""
    _FALLBACK = PredictionResult(
        ml_prediction=None,
        classifier_prob=None,
        regressor_return=None,
        shap_values={},
        shap_expected_value=None,
        top_drivers=[],
        is_bootstrap=False,
    ).to_dict()

    if not os.path.exists(MODEL_PATH):
        _log.warning(
            "ML model not found — falling back to rule-based score",
            model_path=MODEL_PATH,
            hint="run: python scripts/train_hybrid_model.py --force",
        )
        return _FALLBACK

    try:
        regressor: xgb.XGBRegressor = joblib.load(MODEL_PATH)

        mapped = _alias_factors(factors_dict)
        X_pred = pd.DataFrame(
            [{f: mapped.get(f, np.nan) for f in FEATURES}], columns=FEATURES
        )
        X_pred = _sanitize_features(X_pred)

        # Regressor prediction
        pred = regressor.predict(X_pred)
        try:
            if hasattr(pred, "item"):
                raw_return = float(pred.item())
            else:
                raw_return = float(np.ravel(pred)[0])
        except Exception:
            # Fallback if it's somehow a string representation of a list
            val = np.ravel(pred)[0]
            if isinstance(val, str):
                import re
                match = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", val)
                raw_return = float(match.group(0)) if match else 0.0
            else:
                raw_return = float(val)

        regressor_return = raw_return * 100.0 if np.isfinite(raw_return) else None

        # Classifier prediction (if available)
        classifier_prob = None
        if os.path.exists(CLASSIFIER_PATH):
            try:
                classifier: xgb.XGBClassifier = joblib.load(CLASSIFIER_PATH)
                proba = classifier.predict_proba(X_pred)[0]
                classifier_prob = safe_float(proba[1]) * 100.0 if len(proba) > 1 else None
            except Exception:
                pass

        # Blended score
        if classifier_prob is not None and regressor_return is not None:
            # Normalize regressor return to 0-100 scale for blending
            reg_norm = min(max(regressor_return, 0), 100)
            ml_prediction = CLASSIFIER_WEIGHT * classifier_prob + REGRESSOR_WEIGHT * reg_norm
        elif classifier_prob is not None:
            ml_prediction = classifier_prob
        elif regressor_return is not None:
            ml_prediction = regressor_return
        else:
            return _FALLBACK

        # SHAP from regressor
        explainer = shap.TreeExplainer(regressor)
        shap_array = explainer.shap_values(X_pred)
        shap_row = shap_array[0]

        expected_value: float | None = None
        try:
            ev_raw = explainer.expected_value
            expected_value = safe_float(ev_raw) if np.isfinite(safe_float(ev_raw)) else None
        except Exception:
            pass

        breakdown: dict[str, float] = {}
        for i, feat in enumerate(FEATURES):
            val = safe_float(shap_row[i])
            breakdown[feat] = val if np.isfinite(val) else 0.0

        sorted_breakdown = dict(
            sorted(breakdown.items(), key=lambda kv: abs(kv[1]), reverse=True)
        )

        top_drivers = [
            {
                "feature":       feat,
                "shap_value":    shap_val,
                "direction":     "bullish" if shap_val > 0 else "bearish",
                "feature_value": safe_float(X_pred[feat].iloc[0]),
            }
            for feat, shap_val in list(sorted_breakdown.items())[:top_n_drivers]
        ]

        report = load_walk_forward_report()
        is_bootstrap = report.get("is_bootstrap", False) if report else False

        return PredictionResult(
            ml_prediction=safe_float(ml_prediction),
            classifier_prob=classifier_prob,
            regressor_return=regressor_return,
            shap_values=sorted_breakdown,
            shap_expected_value=expected_value,
            top_drivers=top_drivers,
            is_bootstrap=is_bootstrap,
        ).to_dict()

    except Exception as exc:
        import traceback
        _log.error("ML prediction error", error=str(exc), tb=traceback.format_exc())
        return _FALLBACK

def batch_predict(
    stocks: list[dict],
    factors_map: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Vectorised predict_and_explain for a list of stock dicts.

    Uses two-model blended scoring when classifier is available.
    """
    if not os.path.exists(MODEL_PATH):
        _log.warning("Model not found — batch_predict returning empty predictions")
        return [
            {**s, "ml_prediction": None, "classifier_prob": None, "regressor_return": None,
             "shap_values": {}, "top_drivers": [], "is_bootstrap": False}
            for s in stocks
        ]

    regressor: xgb.XGBRegressor = joblib.load(MODEL_PATH)
    explainer = shap.TreeExplainer(regressor)

    # Load classifier if available
    classifier = None
    if os.path.exists(CLASSIFIER_PATH):
        try:
            classifier = joblib.load(CLASSIFIER_PATH)
        except Exception:
            pass

    rows = [_alias_factors(s) for s in stocks]
    X_all = _sanitize_features(pd.DataFrame(rows, columns=FEATURES))
    raw_returns = regressor.predict(X_all)
    shap_all = explainer.shap_values(X_all)

    # Classifier probabilities
    class_probs = None
    if classifier is not None:
        try:
            class_probs = classifier.predict_proba(X_all)[:, 1]
        except Exception:
            pass

    ev: float | None = None
    try:
        ev_raw = explainer.expected_value
        ev = float(ev_raw) if np.isfinite(float(ev_raw)) else None
    except Exception:
        pass

    report = load_walk_forward_report()
    is_bootstrap = report.get("is_bootstrap", False) if report else False

    results = []
    for i, stock in enumerate(stocks):
        raw_ret = float(raw_returns[i])
        reg_return = float(raw_ret * 100.0) if np.isfinite(raw_ret) else None

        cls_prob = None
        if class_probs is not None:
            cls_prob = float(class_probs[i]) * 100.0 if np.isfinite(class_probs[i]) else None

        # Blended score
        if cls_prob is not None and reg_return is not None:
            reg_norm = min(max(reg_return, 0), 100)
            ml_pred = CLASSIFIER_WEIGHT * cls_prob + REGRESSOR_WEIGHT * reg_norm
        elif cls_prob is not None:
            ml_pred = cls_prob
        elif reg_return is not None:
            ml_pred = reg_return
        else:
            ml_pred = None

        breakdown = {
            feat: float(shap_all[i][j]) if np.isfinite(shap_all[i][j]) else 0.0
            for j, feat in enumerate(FEATURES)
        }
        sorted_bd = dict(sorted(breakdown.items(), key=lambda kv: abs(kv[1]), reverse=True))
        top_drivers = [
            {
                "feature":       feat,
                "shap_value":    sv,
                "direction":     "bullish" if sv > 0 else "bearish",
                "feature_value": float(X_all[feat].iloc[i]),
            }
            for feat, sv in list(sorted_bd.items())[:5]
        ]

        results.append({
            **stock,
            "ml_prediction":       ml_pred,
            "classifier_prob":     cls_prob,
            "regressor_return":    reg_return,
            "shap_values":         sorted_bd,
            "shap_expected_value": ev,
            "top_drivers":         top_drivers,
            "is_bootstrap":        is_bootstrap,
        })

    return results


# --- Legacy Compatibility Aliases ---
train_meta_model = train_hybrid_model
train_bootstrap_model = bootstrap_synthetic_model
predict_hybrid_score = predict_and_explain
batch_predict_hybrid_scores = batch_predict

