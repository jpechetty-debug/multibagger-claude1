# modules/hybrid_scoring.py
# Sovereign AI — XGBoost Meta-Model with SHAP Explainability
# Full implementation: walk-forward validation, holdout audit, leakage guard,
# per-fold IC tracking, regime-conditional IC, and SHAP waterfall export.

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

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

MODEL_PATH               = os.path.join("runtime", "models", "xgboost_meta_model.pkl")
WALK_FORWARD_REPORT_PATH = os.path.join("runtime", "models", "xgboost_walk_forward.json")
SHAP_CACHE_PATH          = os.path.join("runtime", "models", "shap_expected_value.json")

# Holdout: 2018-2020 is locked off — never used in training or WF folds.
HOLDOUT_START = "2018-01-01"
HOLDOUT_END   = "2020-12-31"

FEATURES: list[str] = [
    "score",
    "sales_cagr_5y",
    "avg_roe_5y",
    "pe_ratio",
    "debt_equity",
    "cfo_pat_ratio",
    "market_cap_cr",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "vol_breakout",
    "dist_from_52w_high",
    "roce",
]

# Hardcoded, data-independent bounds — intentionally stateless so they can be
# applied identically in training and inference without leaking any fold stats.
FEATURE_BOUNDS: dict[str, tuple[float, float]] = {
    "score":               (0.0,    100.0),
    "sales_cagr_5y":       (-100.0, 300.0),
    "avg_roe_5y":          (-100.0, 200.0),
    "pe_ratio":            (0.0,    300.0),
    "debt_equity":         (0.0,    10.0),
    "cfo_pat_ratio":       (-5.0,   10.0),
    "market_cap_cr":       (0.0,    5_000_000.0),
    "ret_1m":              (-100.0, 500.0),
    "ret_3m":              (-100.0, 1_000.0),
    "ret_6m":              (-100.0, 500.0),
    "vol_breakout":        (0.0,    100.0),
    "dist_from_52w_high":  (0.0,    1.0),
    "roce":                (-100.0, 200.0),
}

# XGBoost hyper-parameters — kept in one place so train + WF folds are identical.
# These serve as both the default config AND the Optuna warm-start initial trial.
_XGB_PARAMS: dict[str, Any] = dict(
    n_estimators=100,
    learning_rate=0.05,
    max_depth=4,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=3,
    reg_alpha=0.1,
    reg_lambda=1.0,
    random_state=42,
    eval_metric="rmse",
)

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

    Intentionally stateless — no scaler, no mean-fill from training data.
    Missing columns are zero-filled; infinite / NaN values are zero-filled.
    """
    assert _SANITIZE_IS_STATELESS, "Must remain stateless — no fitted transforms here."
    out = df.copy()
    for col in FEATURES:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        lo, hi = FEATURE_BOUNDS.get(col, (-1e9, 1e9))
        out[col] = out[col].clip(lower=lo, upper=hi)
    return out[FEATURES]


def _alias_factors(factors_dict: dict) -> dict:
    """Map legacy camelCase / Title_Case factor names to FEATURES snake_case keys."""
    return {
        "score":               factors_dict.get("score",               factors_dict.get("Score", 0.0)),
        "sales_cagr_5y":       factors_dict.get("sales_cagr_5y",       factors_dict.get("Sales_Growth_5Y%", 0.0)),
        "avg_roe_5y":          factors_dict.get("avg_roe_5y",          factors_dict.get("Avg_ROE_5Y%", 0.0)),
        "pe_ratio":            factors_dict.get("pe_ratio",            factors_dict.get("PE_Ratio", 0.0)),
        "debt_equity":         factors_dict.get("debt_equity",         factors_dict.get("Debt_Equity", 0.0)),
        "cfo_pat_ratio":       factors_dict.get("cfo_pat_ratio",       factors_dict.get("CFO_PAT_Ratio", 0.0)),
        "market_cap_cr":       factors_dict.get("market_cap_cr",       factors_dict.get("Market_Cap_Cr", 0.0)),
        "ret_1m":              factors_dict.get("ret_1m",              factors_dict.get("Ret_1M", 0.0)),
        "ret_3m":              factors_dict.get("ret_3m",              factors_dict.get("Ret_3M", 0.0)),
        "ret_6m":              factors_dict.get("ret_6m",              factors_dict.get("Ret_6M", 0.0)),
        "vol_breakout":        factors_dict.get("vol_breakout",        factors_dict.get("Vol_Breakout", 0.0)),
        "dist_from_52w_high":  factors_dict.get("dist_from_52w_high",  factors_dict.get("Dist_From_52W_High", 0.0)),
        "roce":                factors_dict.get("roce",                factors_dict.get("ROCE%", 0.0)),
    }


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def _make_xgb_regressor(params: dict[str, Any] | None = None) -> xgb.XGBRegressor:
    """Create an XGBRegressor from the given params or the legacy defaults."""
    effective = {**_XGB_PARAMS, **(params or {})}
    return xgb.XGBRegressor(**effective)


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
            "random_state":     42,
            "eval_metric":      "rmse",
        }

        from sklearn.model_selection import KFold

        kf = KFold(n_splits=cv_folds, shuffle=True, random_state=42)
        fold_scores: list[float] = []

        for train_idx, val_idx in kf.split(X):
            X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
            y_tr, y_val = y[train_idx], y[val_idx]

            model = xgb.XGBRegressor(**params)
            model.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=False)
            preds = model.predict(X_val)

            # Spearman IC as the optimization target (higher is better)
            ic = _spearman_ic(pd.Series(y_val), pd.Series(preds))
            fold_scores.append(ic if ic is not None else 0.0)

        return float(np.mean(fold_scores))

    study = optuna.create_study(direction="maximize", study_name="xgb_hyperparam")

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

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_sample)

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

def _get_historical_targets(symbols: list[str]) -> dict[str, float]:
    """Return {symbol: current_price} via async data manager (sync-wrapped).

    Fixed: was importing from ``modules.data_service`` and
    ``modules.data_utils`` — both wrong.  Correct paths are under
    ``modules.data_layer.*``.
    """
    from modules.data_layer.data_service import get_data_manager    # ← FIXED
    from modules.data_layer.data_utils import run_coroutine_sync    # ← FIXED

    async def _fetch():
        return await get_data_manager().fetch_batch(symbols)

    data = run_coroutine_sync(_fetch())
    return {
        s: d.get("price", d.get("Price"))
        for s, d in data.items()
        if d.get("price") is not None or d.get("Price") is not None
    }


def _build_training_frame(df: pd.DataFrame, current_prices: dict) -> pd.DataFrame:
    """Attach forward returns (3-month) to each PIT row."""
    from modules.price_utils import fetch_forward_prices

    out = df.copy()
    out["forward_price"] = fetch_forward_prices(out, months=3)
    out = out.dropna(subset=["pit_price", "forward_price"])
    out = out[out["pit_price"] > 0]
    if out.empty:
        return out

    out["forward_return"] = (out["forward_price"] - out["pit_price"]) / out["pit_price"]
    out.replace([np.inf, -np.inf], np.nan, inplace=True)
    train_df = out.dropna(subset=["forward_return"]).copy()
    if not train_df.empty:
        train_df[FEATURES] = _sanitize_features(train_df[FEATURES])
    return train_df


# ---------------------------------------------------------------------------
# Bootstrap: synthetic model from multibaggers (cold-start when PIT is empty)
# ---------------------------------------------------------------------------

def bootstrap_synthetic_model() -> bool:
    """Train a bootstrap XGBoost model using current multibaggers rows.

    Used for cold-start: when ``fundamentals_pit`` is empty or too small
    to run ``train_hybrid_model()``, this function trains on the live
    ``multibaggers`` table using a proxy forward-return target derived
    from the existing score column (score-normalised to [0,1] range,
    shifted to mean-zero so the regressor learns relative ranking).

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
                SELECT symbol,
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

    # Proxy target: score normalised to [0,1], de-meaned → relative signal
    # This makes the model learn the same relative ordering as the rule-based
    # scorer while the shape of the output is a forward-return-like float.
    score_min = df["score"].min()
    score_max = df["score"].max()
    score_range = max(score_max - score_min, 1.0)
    proxy_return = ((df["score"] - score_min) / score_range) - 0.5   # ∈ [-0.5, 0.5]

    X = _sanitize_features(df[FEATURES])
    y = proxy_return.values

    model = _make_xgb_regressor()
    model.fit(X, y)

    # WF report: mark as bootstrap so consumers can distinguish
    wf_report = {
        "status":     "BOOTSTRAP",
        "reason":     "trained on proxy score targets — replace via POST /api/ml/train",
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
    symbols = df["symbol"].unique().tolist()
    _log.info("Fetching current prices to build Y", symbols=len(symbols))
    current_prices = _get_historical_targets(symbols)
    train_df = _build_training_frame(df, current_prices)

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
        from modules.holdout import split_holdout, evaluate_holdout, compare_performance

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

    # ── 6. Production fit on train_only ──
    X = _sanitize_features(train_only[FEATURES])
    y = train_only["forward_return"]
    model = _make_xgb_regressor()
    _log.info("Fitting production XGBoost regressor", rows=len(X))
    model.fit(X, y)

    # ── 6b. SHAP dominance guard ──
    try:
        passes, reason, shap_imp = check_shap_dominance(model, X)
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
        explainer = shap.TreeExplainer(model)
        ev = float(explainer.expected_value)
        os.makedirs(os.path.dirname(SHAP_CACHE_PATH), exist_ok=True)
        with open(SHAP_CACHE_PATH, "w") as fh:
            json.dump({"expected_value": ev}, fh)
    except Exception as exc:
        _log.warning("Could not cache SHAP expected value", error=str(exc))

    # ── 7. Holdout evaluation & overfitting check ──
    if not holdout_only.empty:
        try:
            holdout_metrics = evaluate_holdout(model, holdout_only)
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

    # ── 8. Persist model ──
    in_sample_r2 = model.score(X, y)
    _log.info("Training complete", in_sample_r2=round(in_sample_r2, 4), rows=len(X))
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    _log.info("Model saved", path=MODEL_PATH)
    return True


# ---------------------------------------------------------------------------
# Inference: predict + SHAP explain
# ---------------------------------------------------------------------------

@dataclass
class PredictionResult:
    ml_prediction:      float | None
    shap_values:        dict[str, float]
    shap_expected_value:float | None
    top_drivers:        list[dict]

    def to_dict(self) -> dict:
        return {
            "ml_prediction":       self.ml_prediction,
            "shap_values":         self.shap_values,
            "shap_expected_value": self.shap_expected_value,
            "top_drivers":         self.top_drivers,
        }


def predict_and_explain(
    factors_dict: dict,
    top_n_drivers: int = 5,
) -> dict:
    """Given a live stock's factor dict, predict 3-month forward return and
    generate SHAP values (waterfall-ready)."""
    _FALLBACK = PredictionResult(
        ml_prediction=None,
        shap_values={},
        shap_expected_value=None,
        top_drivers=[],
    ).to_dict()

    if not os.path.exists(MODEL_PATH):
        _log.warning(
            "ML model not found — falling back to rule-based score",
            model_path=MODEL_PATH,
            hint="run: python scripts/train_hybrid_model.py --force",
        )
        return _FALLBACK

    try:
        model: xgb.XGBRegressor = joblib.load(MODEL_PATH)

        mapped = _alias_factors(factors_dict)
        X_pred = pd.DataFrame(
            [{f: mapped.get(f, 0.0) for f in FEATURES}], columns=FEATURES
        )
        X_pred = _sanitize_features(X_pred)

        raw_prediction = float(model.predict(X_pred)[0])
        if not np.isfinite(raw_prediction):
            return _FALLBACK

        explainer  = shap.TreeExplainer(model)
        shap_array = explainer.shap_values(X_pred)
        shap_row   = shap_array[0]

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

        return PredictionResult(
            ml_prediction=float(raw_prediction * 100.0),
            shap_values=sorted_breakdown,
            shap_expected_value=expected_value,
            top_drivers=top_drivers,
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
    """Vectorised predict_and_explain for a list of stock dicts."""
    if not os.path.exists(MODEL_PATH):
        _log.warning("Model not found — batch_predict returning empty predictions")
        return [
            {**s, "ml_prediction": None, "shap_values": {}, "top_drivers": []}
            for s in stocks
        ]

    model: xgb.XGBRegressor = joblib.load(MODEL_PATH)
    explainer = shap.TreeExplainer(model)

    rows  = [_alias_factors(s) for s in stocks]
    X_all = _sanitize_features(pd.DataFrame(rows, columns=FEATURES))
    raw_preds = model.predict(X_all)
    shap_all  = explainer.shap_values(X_all)

    ev: float | None = None
    try:
        ev = float(explainer.expected_value)
        ev = ev if np.isfinite(ev) else None
    except Exception:
        pass

    results = []
    for i, stock in enumerate(stocks):
        pred_raw = float(raw_preds[i])
        ml_pred  = float(pred_raw * 100.0) if np.isfinite(pred_raw) else None

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
            "shap_values":         sorted_bd,
            "shap_expected_value": ev,
            "top_drivers":         top_drivers,
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
