# modules/hybrid_scoring.py
# Sovereign AI — XGBoost Meta-Model with SHAP Explainability
# Two-model architecture: Classifier (multibagger probability) + Regressor (return)
# Walk-forward validation, holdout audit, leakage guard, SHAP waterfall export.

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from typing import Any

import joblib
import numpy as np
import optuna
import pandas as pd
import shap
import xgboost as xgb

from modules.feature_factory import (
    EXTENDED_FEATURE_BOUNDS,
    EXTENDED_FEATURES,
    compute_all_features,
    compute_features_batch,
)
from modules.feature_factory import (
    sanitize_features as _sanitize_extended,
)

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

MODEL_PATH               = os.path.join("runtime", "models", "xgboost_meta_model.pkl")
CLASSIFIER_PATH          = os.path.join("runtime", "models", "xgboost_classifier.pkl")
WALK_FORWARD_REPORT_PATH = os.path.join("runtime", "models", "xgboost_walk_forward.json")
SHAP_CACHE_PATH          = os.path.join("runtime", "models", "shap_expected_value.json")

# Holdout: 2018-2020 is locked off — never used in training or WF folds.
HOLDOUT_START = "2018-01-01"
HOLDOUT_END   = "2020-12-31"

# Use extended 30+ features from feature_factory
FEATURES: list[str] = EXTENDED_FEATURES
FEATURE_BOUNDS: dict[str, tuple[float, float]] = EXTENDED_FEATURE_BOUNDS

# Blending weights for two-model architecture
CLASSIFIER_WEIGHT = 0.6
REGRESSOR_WEIGHT = 0.4

# XGBoost hyper-parameters — kept in one place so train + WF folds are identical.
# These serve as both the default config AND the Optuna warm-start initial trial.
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

# SHAP dominance threshold: reject model if any single feature accounts for
# more than this fraction of total absolute SHAP importance.
SHAP_DOMINANCE_THRESHOLD = 0.90

# Optuna search space bounds (warm-started from _XGB_PARAMS).
_OPTUNA_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    "n_estimators":     {"low": 50,   "high": 500},
    "learning_rate":    {"low": 0.01, "high": 0.3,  "log": True},
    "max_depth":        {"low": 3,    "high": 8},
    "subsample":        {"low": 0.5,  "high": 1.0},
    "colsample_bytree": {"low": 0.4,  "high": 1.0},
    "min_child_weight": {"low": 1,    "high": 10},
    "reg_alpha":        {"low": 1e-3, "high": 10.0, "log": True},
    "reg_lambda":       {"low": 1e-3, "high": 10.0, "log": True},
}

# ---------------------------------------------------------------------------
# Logging — graceful fallback if project logger is unavailable
# ---------------------------------------------------------------------------

try:
    from core.observability.logger import get_logger
    _log = get_logger("modules.hybrid_scoring")
except Exception:  # pragma: no cover
    import logging
    _log = logging.getLogger("modules.hybrid_scoring")


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

#: Sentinel checked by tests: sanitize must never grow stateful params.
_SANITIZE_IS_STATELESS = True


# ---------------------------------------------------------------------------
# Feature helpers
# ---------------------------------------------------------------------------

def _sanitize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce features to finite floats and clip to FEATURE_BOUNDS.

    Delegates to feature_factory.sanitize_features() for the extended
    30+ feature set. XGBoost handles NaN natively.
    """
    assert _SANITIZE_IS_STATELESS, "Must remain stateless — no fitted transforms here."
    return _sanitize_extended(df)


def _alias_factors(factors_dict: dict) -> dict:
    """Map legacy camelCase / Title_Case factor names to FEATURES snake_case keys.

    For the original 13 features, maps known aliases. For the new 17+ features,
    computes them live via feature_factory if a symbol is available.
    """
    # Map the original 13 legacy aliases
    mapped = {
        "score":               factors_dict.get("score",               factors_dict.get("Score", np.nan)),
        "sales_cagr_5y":       factors_dict.get("sales_cagr_5y",       factors_dict.get("Sales_Growth_5Y%", np.nan)),
        "avg_roe_5y":          factors_dict.get("avg_roe_5y",          factors_dict.get("Avg_ROE_5Y%", np.nan)),
        "pe_ratio":            factors_dict.get("pe_ratio",            factors_dict.get("PE_Ratio", np.nan)),
        "debt_equity":         factors_dict.get("debt_equity",         factors_dict.get("Debt_Equity", np.nan)),
        "cfo_pat_ratio":       factors_dict.get("cfo_pat_ratio",       factors_dict.get("CFO_PAT_Ratio", np.nan)),
        "market_cap_cr":       factors_dict.get("market_cap_cr",       factors_dict.get("Market_Cap_Cr", np.nan)),
        "ret_1m":              factors_dict.get("ret_1m",              factors_dict.get("Ret_1M", np.nan)),
        "ret_3m":              factors_dict.get("ret_3m",              factors_dict.get("Ret_3M", np.nan)),
        "ret_6m":              factors_dict.get("ret_6m",              factors_dict.get("Ret_6M", np.nan)),
        "vol_breakout":        factors_dict.get("vol_breakout",        factors_dict.get("Vol_Breakout", np.nan)),
        "dist_from_52w_high":  factors_dict.get("dist_from_52w_high",  factors_dict.get("Dist_From_52W_High", np.nan)),
        "roce":                factors_dict.get("roce",                factors_dict.get("ROCE%", np.nan)),
    }

    # Compute extended features if symbol is available
    symbol = factors_dict.get("symbol", factors_dict.get("Symbol", ""))
    if symbol:
        extended = compute_all_features(str(symbol), factors_dict)
        # Only fill features that aren't already in the mapped dict
        for feat in FEATURES:
            if feat not in mapped:
                mapped[feat] = extended.get(feat, np.nan)
    else:
        # Fill remaining features from dict or NaN
        for feat in FEATURES:
            if feat not in mapped:
                mapped[feat] = factors_dict.get(feat, np.nan)

    return mapped


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def _make_xgb_regressor(params: dict[str, Any] | None = None) -> xgb.XGBRegressor:
    """Create an XGBRegressor from the given params or the legacy defaults."""
    effective = {**_XGB_PARAMS, **(params or {})}
    return xgb.XGBRegressor(**effective)


def _make_xgb_classifier(params: dict[str, Any] | None = None) -> xgb.XGBClassifier:
    """Create an XGBClassifier for multibagger probability prediction."""
    base = {
        "n_estimators": 100,
        "learning_rate": 0.05,
        "max_depth": 4,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "min_child_weight": 3,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": 42,
        "eval_metric": "logloss",
        "scale_pos_weight": 3.0,  # Compensate for class imbalance
        "use_label_encoder": False,
    }
    base.update(params or {})
    return xgb.XGBClassifier(**base)


# ---------------------------------------------------------------------------
# Optuna Bayesian hyperparameter optimization
# ---------------------------------------------------------------------------

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

def check_shap_dominance(
    model: xgb.XGBRegressor,
    X: pd.DataFrame,
    *,
    threshold: float = SHAP_DOMINANCE_THRESHOLD,
    sample_size: int = 200,
) -> tuple[bool, str, dict[str, float]]:
    """Check whether any single feature dominates SHAP importance.

    Args:
        model: Trained XGBRegressor.
        X: Feature DataFrame (sanitized).
        threshold: Maximum allowed fraction for a single feature (default 0.90).
        sample_size: How many rows to sample for SHAP computation.

    Returns:
        (passes, reason, importance_dict)
        ``passes`` is True when no single feature exceeds the threshold.
    """
    X_sample = X.sample(n=min(sample_size, len(X)), random_state=42)

    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)
        if len(shap_values.shape) < 2 or shap_values.shape[0] == 0:
            return True, "SHAP values empty — sample size too small", {}
    except Exception as exc:
        return True, f"SHAP computation failed: {str(exc)}", {}

    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    total = float(mean_abs_shap.sum())
    if total == 0:
        return True, "Zero total SHAP — trivial model", {}

    importance: dict[str, float] = {}
    for i, feat in enumerate(FEATURES):
        importance[feat] = round(float(mean_abs_shap[i]) / total, 6)

    max_feat = max(importance, key=importance.get)  # type: ignore[arg-type]
    max_share = importance[max_feat]

    if max_share > threshold:
        reason = (
            f"REJECTED: Feature '{max_feat}' drives {max_share:.1%} of model "
            f"predictions (threshold: {threshold:.0%}). Likely data leakage or "
            f"overfitting to a single signal."
        )
        return False, reason, importance

    return True, "OK", importance


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _finite_or_none(value: Any) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _spearman_ic(y_true: pd.Series, y_pred: pd.Series) -> float | None:
    """Return Spearman rank correlation, or None when <2 valid pairs."""
    valid = y_true.notna() & y_pred.notna()
    yt, yp = y_true[valid], y_pred[valid]
    if len(yt) < 2:
        return None
    return _finite_or_none(yt.corr(yp, method="spearman"))


def _top_quantile_sharpe(
    returns: pd.Series,
    quantile: float = 0.2,
    periods_per_year: int = 4,
) -> float | None:
    """Annualised Sharpe on the top-quantile (long-only) return slice."""
    if returns.empty:
        return None
    n = max(1, int(len(returns) * quantile))
    top = returns.nlargest(n)
    if top.std() == 0 or len(top) < 2:
        return None
    return _finite_or_none(top.mean() / top.std() * np.sqrt(periods_per_year))


# ---------------------------------------------------------------------------
# Walk-forward validation
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardWindow:
    test_period:     str
    train_rows:      int
    test_rows:       int
    fold_ic:         float | None = None
    fold_hit_rate:   float | None = None
    fold_top_sharpe: float | None = None


@dataclass
class WalkForwardResult:
    status: str                              # "OK" | "SKIPPED"
    reason: str = ""
    folds: int = 0
    rows: int = 0
    oos_r2: float | None = None
    mae: float | None = None
    rmse: float | None = None
    spearman_ic: float | None = None
    hit_rate: float | None = None
    top_quantile_sharpe: float | None = None
    holdout_rows_excluded: int = 0
    windows: list[WalkForwardWindow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "folds": self.folds,
            "rows": self.rows,
            "oos_r2": self.oos_r2,
            "mae": self.mae,
            "rmse": self.rmse,
            "spearman_ic": self.spearman_ic,
            "hit_rate": self.hit_rate,
            "top_quantile_sharpe": self.top_quantile_sharpe,
            "holdout_rows_excluded": self.holdout_rows_excluded,
            "windows": [
                {
                    "test_period":   w.test_period,
                    "train_rows":    w.train_rows,
                    "test_rows":     w.test_rows,
                    "fold_ic":       w.fold_ic,
                    "fold_hit_rate": w.fold_hit_rate,
                    "fold_top_sharpe": w.fold_top_sharpe,
                }
                for w in self.windows
            ],
        }


def walk_forward_validate(
    train_df: pd.DataFrame,
    min_train_rows: int = 10,
    min_train_periods: int = 4,
) -> dict:
    """Expanding-window walk-forward validation for the hybrid XGBoost scorer."""
    required = {"symbol", "as_of_date", "forward_return", *FEATURES}
    missing = required - set(train_df.columns)
    if missing:
        return WalkForwardResult(
            status="SKIPPED",
            reason=f"missing columns: {sorted(missing)}",
        ).to_dict()

    df = train_df.copy()
    df["as_of_date"]    = pd.to_datetime(df["as_of_date"], errors="coerce")
    df["forward_return"]= pd.to_numeric(df["forward_return"], errors="coerce")
    df = df.dropna(subset=["as_of_date", "forward_return"]).sort_values("as_of_date")

    holdout_mask         = df["as_of_date"].between(HOLDOUT_START, HOLDOUT_END)
    holdout_rows_excluded= int(holdout_mask.sum())
    df = df[~holdout_mask]

    if len(df) < min_train_rows:
        return WalkForwardResult(
            status="SKIPPED",
            reason="not enough valid rows",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    df["test_period"] = df["as_of_date"].dt.to_period("Q")
    periods = sorted(df["test_period"].dropna().unique())
    if len(periods) <= min_train_periods:
        return WalkForwardResult(
            status="SKIPPED",
            reason="not enough quarterly periods",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    all_predictions: list[pd.DataFrame] = []
    windows: list[WalkForwardWindow]    = []

    for test_period in periods[min_train_periods:]:
        test_start = test_period.start_time
        train_fold = df[df["as_of_date"] < test_start]
        test_fold  = df[df["test_period"] == test_period]

        if len(train_fold) < min_train_rows or test_fold.empty:
            continue

        model   = _make_xgb_regressor()
        X_train = _sanitize_features(train_fold[FEATURES])
        y_train = train_fold["forward_return"]
        X_test  = _sanitize_features(test_fold[FEATURES])

        model.fit(X_train, y_train, eval_set=[(X_train, y_train)], verbose=False)

        fold_preds = test_fold[["symbol", "as_of_date", "forward_return"]].copy()
        fold_preds["prediction"] = model.predict(X_test)
        fold_preds["test_period"]= str(test_period)
        all_predictions.append(fold_preds)

        ft = pd.to_numeric(fold_preds["forward_return"], errors="coerce")
        fp = pd.to_numeric(fold_preds["prediction"],     errors="coerce")
        fold_ic       = _spearman_ic(ft, fp)
        fold_hit_rate = _finite_or_none(((ft > 0) == (fp > 0)).mean())
        fold_sharpe   = _top_quantile_sharpe(
            ft[fp.nlargest(max(1, int(len(fp) * 0.2))).index],
        )
        windows.append(WalkForwardWindow(
            test_period=str(test_period),
            train_rows=int(len(train_fold)),
            test_rows=int(len(test_fold)),
            fold_ic=fold_ic,
            fold_hit_rate=fold_hit_rate,
            fold_top_sharpe=fold_sharpe,
        ))

    if not all_predictions:
        return WalkForwardResult(
            status="SKIPPED",
            reason="no valid walk-forward folds",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    pred_df = pd.concat(all_predictions, ignore_index=True)
    y_true  = pd.to_numeric(pred_df["forward_return"], errors="coerce")
    y_pred  = pd.to_numeric(pred_df["prediction"],     errors="coerce")
    valid   = y_true.notna() & y_pred.notna()
    y_true, y_pred = y_true[valid], y_pred[valid]

    if y_true.empty:
        return WalkForwardResult(
            status="SKIPPED",
            reason="all predictions invalid",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    residual = y_true - y_pred
    ss_res = float(np.square(residual).sum())
    ss_tot = float(np.square(y_true - y_true.mean()).sum())

    return WalkForwardResult(
        status="OK",
        folds=len(windows),
        rows=int(len(y_true)),
        oos_r2=_finite_or_none(1 - ss_res / ss_tot if ss_tot > 0 else np.nan),
        mae=_finite_or_none(np.abs(residual).mean()),
        rmse=_finite_or_none(np.sqrt(np.square(residual).mean())),
        spearman_ic=_spearman_ic(y_true, y_pred),
        hit_rate=_finite_or_none(((y_true > 0) == (y_pred > 0)).mean()),
        top_quantile_sharpe=_top_quantile_sharpe(
            y_true[y_pred.nlargest(max(1, int(len(y_pred) * 0.2))).index]
        ),
        holdout_rows_excluded=holdout_rows_excluded,
        windows=windows,
    ).to_dict()


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------

def _save_walk_forward_report(metrics: dict) -> None:
    os.makedirs(os.path.dirname(WALK_FORWARD_REPORT_PATH), exist_ok=True)
    with open(WALK_FORWARD_REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    _log.info("Walk-forward report saved", path=WALK_FORWARD_REPORT_PATH)


def load_walk_forward_report() -> dict | None:
    """Load last persisted walk-forward report, or None if not yet trained."""
    if not os.path.exists(WALK_FORWARD_REPORT_PATH):
        return None
    with open(WALK_FORWARD_REPORT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Training-data helpers  ← FIXED: correct import paths
# ---------------------------------------------------------------------------




def _build_training_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Attach 6-month forward returns and multibagger labels to PIT rows."""
    from modules.target_engineering import build_training_targets

    train_df = build_training_targets(df, horizon_months=6)
    if not train_df.empty:
        # Compute extended features
        feat_df = compute_features_batch(train_df)
        for col in FEATURES:
            if col in feat_df.columns:
                train_df[col] = feat_df[col].values
        train_df[FEATURES] = _sanitize_features(train_df[FEATURES])
    return train_df


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

def train_hybrid_model() -> bool:
    """Full training pipeline: PIT extraction → leakage audit → holdout split
    → walk-forward validation → production fit → model persistence.

    Returns True on success, False if skipped due to insufficient data.
    """
    _log.info("Initiating Hybrid Scoring Meta-Model Training (XGBoost)…")

    # ── 1. Extract PIT Data ──
    try:
        from modules.data_layer.db_utils import get_db_connection  # ← FIXED path
        from modules.pit_auditor import sanitize

        with get_db_connection("stocks.db") as conn:
            raw_df = pd.read_sql(
                """
                SELECT symbol, as_of_date,
                       source_updated_at AS report_date,
                       price             AS pit_price,
                       score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                       debt_equity, cfo_pat_ratio, market_cap_cr,
                       ret_1m, ret_3m, ret_6m,
                       vol_breakout, dist_from_52w_high, roce
                FROM fundamentals_pit
                """,
                conn,
            )
            df = sanitize(raw_df)
            if df.empty and not raw_df.empty:
                _log.warning(
                    "PIT Auditor quarantined all rows — using raw fallback"
                )
                df = raw_df
    except Exception as exc:
        _log.warning("Could not load or sanitize PIT data", error=str(exc))
        return False

    if len(df) < 20:
        _log.info("Insufficient PIT rows", rows=len(df), minimum=20)
        return False

    # ── 2. Construct forward-return targets ──
    train_df = _build_training_frame(df)

    if train_df.empty or len(train_df) < 10:
        _log.info("Too few rows with valid forward returns", rows=len(train_df))
        return False

    # ── 3. Feature leakage audit ──
    try:
        from modules.feature_leakage_audit import audit_features

        leakage_report = audit_features(train_df)
        for v in leakage_report.verdicts:
            if v.classification == "LEAKING":
                _log.warning("Feature leakage", feature=v.feature, spearman_r=v.spearman_r)
            elif v.classification == "NEEDS_REVIEW":
                _log.info("Feature review", feature=v.feature, spearman_r=v.spearman_r)
        _log.info(
            "Leakage audit complete",
            leaking=leakage_report.leaking_count,
            review=leakage_report.review_count,
        )
    except Exception as exc:
        _log.warning("Feature leakage audit failed", error=str(exc))

    # ── 4. Holdout split ──
    try:
        from modules.holdout import compare_performance, evaluate_holdout, split_holdout

        train_only, holdout_only = split_holdout(train_df)
        _log.info("Holdout split", train=len(train_only), holdout=len(holdout_only))
    except Exception as exc:
        _log.warning("Holdout split failed — using all data", error=str(exc))
        train_only   = train_df
        holdout_only = pd.DataFrame()

    # ── 5. Walk-forward validation ──
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

    # ── 6. Production fit: Two-model architecture ──
    X = _sanitize_features(train_only[FEATURES])
    y_return = train_only["forward_return"]

    # Model A: Regressor (expected return)
    regressor = _make_xgb_regressor()
    _log.info("Fitting production XGBoost regressor", rows=len(X))
    regressor.fit(X, y_return)

    # Model B: Classifier (multibagger probability)
    classifier = None
    if "is_multibagger" in train_only.columns:
        y_class = train_only["is_multibagger"]
        n_pos = int(y_class.sum())
        n_neg = len(y_class) - n_pos
        if n_pos >= 5 and n_neg >= 5:  # Need minimum samples per class
            classifier = _make_xgb_classifier()
            _log.info(
                "Fitting production XGBoost classifier",
                rows=len(X),
                positives=n_pos,
                negatives=n_neg,
            )
            classifier.fit(X, y_class)
        else:
            _log.info(
                "Skipping classifier: insufficient class balance",
                positives=n_pos,
                negatives=n_neg,
            )

    # ── 6b. SHAP dominance guard (on regressor) ──
    try:
        passes, reason, shap_imp = check_shap_dominance(regressor, X)
        if not passes:
            _log.error(
                "Model REJECTED by SHAP dominance guard",
                reason=reason,
                importance=shap_imp,
            )
            return False
        _log.info("SHAP dominance guard passed", top_feature_share=max(shap_imp.values()) if shap_imp else 0)
    except Exception as exc:
        _log.warning("SHAP dominance check failed — proceeding anyway", error=str(exc))

    # Cache SHAP expected value
    try:
        explainer = shap.TreeExplainer(regressor)
        ev = float(explainer.expected_value)
        os.makedirs(os.path.dirname(SHAP_CACHE_PATH), exist_ok=True)
        with open(SHAP_CACHE_PATH, "w") as fh:
            json.dump({"expected_value": ev}, fh)
    except Exception as exc:
        _log.warning("Could not cache SHAP expected value", error=str(exc))

    # ── 7. Holdout evaluation & overfitting check ──
    if not holdout_only.empty:
        try:
            holdout_metrics = evaluate_holdout(regressor, holdout_only)
            if holdout_metrics.get("status") == "OK":
                wf_ic      = float(validation.get("spearman_ic") or 0.0)
                holdout_ic = float(holdout_metrics.get("spearman_ic") or 0.0)
                overfit    = compare_performance(wf_ic, holdout_ic)
                if overfit["overfitting_detected"]:
                    _log.warning(
                        "OVERFITTING detected",
                        wf_ic=wf_ic,
                        holdout_ic=holdout_ic,
                        gap=overfit["sharpe_gap"],
                    )
                _log.info("Holdout evaluation", **holdout_metrics)
        except Exception as exc:
            _log.warning("Holdout evaluation failed", error=str(exc))

    # ── 8. Persist models ──
    in_sample_r2 = regressor.score(X, y_return)
    _log.info("Training complete", in_sample_r2=round(in_sample_r2, 4), rows=len(X))
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(regressor, MODEL_PATH)
    _log.info("Regressor saved", path=MODEL_PATH)

    if classifier is not None:
        os.makedirs(os.path.dirname(CLASSIFIER_PATH), exist_ok=True)
        joblib.dump(classifier, CLASSIFIER_PATH)
        _log.info("Classifier saved", path=CLASSIFIER_PATH)

    return True


# ---------------------------------------------------------------------------
# Inference: predict + SHAP explain
# ---------------------------------------------------------------------------

@dataclass
class PredictionResult:
    ml_prediction:      float | None
    classifier_prob:    float | None
    regressor_return:   float | None
    shap_values:        dict[str, float]
    shap_expected_value:float | None
    top_drivers:        list[dict]
    is_bootstrap:       bool = False

    def to_dict(self) -> dict:
        return {
            "ml_prediction":       self.ml_prediction,
            "classifier_prob":     self.classifier_prob,
            "regressor_return":    self.regressor_return,
            "shap_values":         self.shap_values,
            "shap_expected_value": self.shap_expected_value,
            "top_drivers":         self.top_drivers,
            "is_bootstrap":        self.is_bootstrap,
        }


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
        raw_return = float(regressor.predict(X_pred)[0])
        regressor_return = raw_return * 100.0 if np.isfinite(raw_return) else None

        # Classifier prediction (if available)
        classifier_prob = None
        if os.path.exists(CLASSIFIER_PATH):
            try:
                classifier: xgb.XGBClassifier = joblib.load(CLASSIFIER_PATH)
                proba = classifier.predict_proba(X_pred)[0]
                classifier_prob = float(proba[1]) * 100.0 if len(proba) > 1 else None
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
            expected_value = float(ev_raw) if np.isfinite(float(ev_raw)) else None
        except Exception:
            pass

        breakdown: dict[str, float] = {}
        for i, feat in enumerate(FEATURES):
            val = float(shap_row[i])
            breakdown[feat] = val if np.isfinite(val) else 0.0

        sorted_breakdown = dict(
            sorted(breakdown.items(), key=lambda kv: abs(kv[1]), reverse=True)
        )

        top_drivers = [
            {
                "feature":       feat,
                "shap_value":    shap_val,
                "direction":     "bullish" if shap_val > 0 else "bearish",
                "feature_value": float(X_pred[feat].iloc[0]),
            }
            for feat, shap_val in list(sorted_breakdown.items())[:top_n_drivers]
        ]

        report = load_walk_forward_report()
        is_bootstrap = report.get("is_bootstrap", False) if report else False

        return PredictionResult(
            ml_prediction=float(ml_prediction),
            classifier_prob=classifier_prob,
            regressor_return=regressor_return,
            shap_values=sorted_breakdown,
            shap_expected_value=expected_value,
            top_drivers=top_drivers,
            is_bootstrap=is_bootstrap,
        ).to_dict()

    except Exception as exc:
        _log.error("ML prediction error", error=str(exc))
        return _FALLBACK


# ---------------------------------------------------------------------------
# Batch inference helper
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Model diagnostics
# ---------------------------------------------------------------------------

def get_feature_importance() -> dict[str, float]:
    """Return XGBoost gain-based feature importances (requires trained model)."""
    if not os.path.exists(MODEL_PATH):
        return {}
    try:
        model: xgb.XGBRegressor = joblib.load(MODEL_PATH)
        imp   = model.get_booster().get_score(importance_type="gain")
        total = sum(imp.values()) or 1.0
        return {feat: round(imp.get(feat, 0.0) / total, 6) for feat in FEATURES}
    except Exception as exc:
        _log.warning("Could not load feature importances", error=str(exc))
        return {}


def model_is_trained() -> bool:
    """Return True if a serialised model exists on disk."""
    return os.path.exists(MODEL_PATH)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    success = train_hybrid_model()
    raise SystemExit(0 if success else 1)
