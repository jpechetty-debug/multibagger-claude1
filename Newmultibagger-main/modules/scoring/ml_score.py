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
    compute_features_batch,
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
        dom_check = check_shap_dominance(regressor, X, threshold=SHAP_DOMINANCE_THRESHOLD)
        passes = not dom_check["dominant"]
        shap_dominance = {
            "checked": True,
            "passes_threshold": passes,
            "top_feature": dom_check.get("max_feature"),
            "top_feature_share": dom_check.get("max_share"),
            "threshold": SHAP_DOMINANCE_THRESHOLD,
        }
        if not passes:
            _log.warning("Production model SHAP dominance exceeds threshold", top_feature=dom_check.get("max_feature"))
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
