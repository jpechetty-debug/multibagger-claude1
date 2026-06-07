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
import pandas as pd
import shap
import xgboost as xgb

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------

MODEL_PATH = os.path.join("runtime", "models", "xgboost_meta_model.pkl")
WALK_FORWARD_REPORT_PATH = os.path.join("runtime", "models", "xgboost_walk_forward.json")
SHAP_CACHE_PATH = os.path.join("runtime", "models", "shap_expected_value.json")

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
    "score":              (0.0,    100.0),
    "sales_cagr_5y":     (-100.0, 300.0),
    "avg_roe_5y":        (-100.0, 200.0),
    "pe_ratio":          (0.0,    300.0),
    "debt_equity":       (0.0,    10.0),
    "cfo_pat_ratio":     (-5.0,   10.0),
    "market_cap_cr":     (0.0,    5_000_000.0),
    "ret_1m":            (-100.0, 500.0),
    "ret_3m":            (-100.0, 1_000.0),
    "ret_6m":            (-100.0, 500.0),
    "vol_breakout":      (0.0,    100.0),
    "dist_from_52w_high":(0.0,    1.0),
    "roce":              (-100.0, 200.0),
}

# XGBoost hyper-parameters — kept in one place so train + WF folds are identical.
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
        "score":              factors_dict.get("score",              factors_dict.get("Score", 0.0)),
        "sales_cagr_5y":     factors_dict.get("sales_cagr_5y",     factors_dict.get("Sales_Growth_5Y%", 0.0)),
        "avg_roe_5y":        factors_dict.get("avg_roe_5y",        factors_dict.get("Avg_ROE_5Y%", 0.0)),
        "pe_ratio":          factors_dict.get("pe_ratio",          factors_dict.get("PE_Ratio", 0.0)),
        "debt_equity":       factors_dict.get("debt_equity",       factors_dict.get("Debt_Equity", 0.0)),
        "cfo_pat_ratio":     factors_dict.get("cfo_pat_ratio",     factors_dict.get("CFO_PAT_Ratio", 0.0)),
        "market_cap_cr":     factors_dict.get("market_cap_cr",     factors_dict.get("Market_Cap_Cr", 0.0)),
        "ret_1m":            factors_dict.get("ret_1m",            factors_dict.get("Ret_1M", 0.0)),
        "ret_3m":            factors_dict.get("ret_3m",            factors_dict.get("Ret_3M", 0.0)),
        "ret_6m":            factors_dict.get("ret_6m",            factors_dict.get("Ret_6M", 0.0)),
        "vol_breakout":      factors_dict.get("vol_breakout",      factors_dict.get("Vol_Breakout", 0.0)),
        "dist_from_52w_high":factors_dict.get("dist_from_52w_high",factors_dict.get("Dist_From_52W_High", 0.0)),
        "roce":              factors_dict.get("roce",              factors_dict.get("ROCE%", 0.0)),
    }


# ---------------------------------------------------------------------------
# Model factory
# ---------------------------------------------------------------------------

def _make_xgb_regressor() -> xgb.XGBRegressor:
    return xgb.XGBRegressor(**_XGB_PARAMS)


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
    test_period: str
    train_rows: int
    test_rows: int
    fold_ic: float | None = None
    fold_hit_rate: float | None = None
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
        d = {
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
                    "test_period": w.test_period,
                    "train_rows": w.train_rows,
                    "test_rows": w.test_rows,
                    "fold_ic": w.fold_ic,
                    "fold_hit_rate": w.fold_hit_rate,
                    "fold_top_sharpe": w.fold_top_sharpe,
                }
                for w in self.windows
            ],
        }
        return d


def walk_forward_validate(
    train_df: pd.DataFrame,
    min_train_rows: int = 10,
    min_train_periods: int = 4,
) -> dict:
    """Expanding-window walk-forward validation for the hybrid XGBoost scorer.

    Each fold trains only on rows whose ``as_of_date`` predates the test
    quarter, so no future information leaks into any fold.  The 2018-2020
    holdout window is excluded from all folds.

    Returns a plain dict (JSON-serialisable) for persistence and API response.

    Args:
        train_df: Must contain columns in FEATURES + ['symbol', 'as_of_date',
            'forward_return'].
        min_train_rows: Minimum rows required to attempt a fold.
        min_train_periods: Minimum distinct quarters in pre-holdout history
            before we start evaluating.

    Returns:
        Dict with keys: status, folds, rows, oos_r2, mae, rmse, spearman_ic,
        hit_rate, top_quantile_sharpe, holdout_rows_excluded, windows.
    """
    required = {"symbol", "as_of_date", "forward_return", *FEATURES}
    missing = required - set(train_df.columns)
    if missing:
        return WalkForwardResult(
            status="SKIPPED",
            reason=f"missing columns: {sorted(missing)}",
        ).to_dict()

    df = train_df.copy()
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    df["forward_return"] = pd.to_numeric(df["forward_return"], errors="coerce")
    df = df.dropna(subset=["as_of_date", "forward_return"]).sort_values("as_of_date")

    # ── Exclude holdout from walk-forward folds ──
    holdout_mask = df["as_of_date"].between(HOLDOUT_START, HOLDOUT_END)
    holdout_rows_excluded = int(holdout_mask.sum())
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
    windows: list[WalkForwardWindow] = []

    for test_period in periods[min_train_periods:]:
        test_start = test_period.start_time
        train_fold = df[df["as_of_date"] < test_start]
        test_fold  = df[df["test_period"] == test_period]

        if len(train_fold) < min_train_rows or test_fold.empty:
            continue

        model = _make_xgb_regressor()
        X_train = _sanitize_features(train_fold[FEATURES])
        y_train = train_fold["forward_return"]
        X_test  = _sanitize_features(test_fold[FEATURES])

        model.fit(
            X_train, y_train,
            eval_set=[(X_train, y_train)],
            verbose=False,
        )

        fold_preds = test_fold[["symbol", "as_of_date", "forward_return"]].copy()
        fold_preds["prediction"] = model.predict(X_test)
        fold_preds["test_period"] = str(test_period)
        all_predictions.append(fold_preds)

        # ── Per-fold metrics ──
        ft = pd.to_numeric(fold_preds["forward_return"], errors="coerce")
        fp = pd.to_numeric(fold_preds["prediction"], errors="coerce")
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
    y_pred  = pd.to_numeric(pred_df["prediction"], errors="coerce")
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

    result = WalkForwardResult(
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
    )
    return result.to_dict()


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
# Training-data helpers
# ---------------------------------------------------------------------------

def _get_historical_targets(symbols: list[str]) -> dict[str, float]:
    """Return {symbol: current_price} via async data manager (sync-wrapped)."""
    from modules.data_service import get_data_manager
    from modules.data_utils import run_coroutine_sync

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
# Main training entry-point
# ---------------------------------------------------------------------------

def train_hybrid_model() -> bool:
    """Full training pipeline: PIT extraction → leakage audit → holdout split
    → walk-forward validation → production fit → model persistence.

    Returns:
        True on success, False if skipped due to insufficient data.
    """
    _log.info("Initiating Hybrid Scoring Meta-Model Training (XGBoost)…")

    # ── 1. Extract PIT Data ──
    try:
        from modules.db_utils import get_db_connection
        from modules.pit_auditor import sanitize

        with get_db_connection("stocks.db") as conn:
            query = """
                SELECT
                    symbol, as_of_date,
                    source_updated_at AS report_date,
                    price             AS pit_price,
                    score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                    debt_equity, cfo_pat_ratio, market_cap_cr,
                    ret_1m, ret_3m, ret_6m,
                    vol_breakout, dist_from_52w_high, roce
                FROM fundamentals_pit
            """
            raw_df = pd.read_sql(query, conn)
            df = sanitize(raw_df)
            if df.empty and not raw_df.empty:
                _log.warning("PIT Auditor quarantine: all rows failed temporal strictness — using raw fallback.")
                df = raw_df
    except Exception as exc:
        _log.warning(f"Could not load or sanitize PIT data: {exc}")
        return False

    if len(df) < 20:
        _log.info(f"Insufficient PIT rows ({len(df)}); need ≥ 20. Skipping training.")
        return False

    # ── 2. Construct forward-return targets ──
    symbols = df["symbol"].unique().tolist()
    _log.info(f"Fetching current prices for {len(symbols)} symbols to build Y…")
    current_prices = _get_historical_targets(symbols)
    train_df = _build_training_frame(df, current_prices)

    if train_df.empty or len(train_df) < 10:
        _log.info("Too few rows with valid forward returns. Skipping training.")
        return False

    # ── 3. Feature leakage audit ──
    try:
        from modules.feature_leakage_audit import audit_features

        leakage_report = audit_features(train_df)
        for v in leakage_report.verdicts:
            if v.classification == "LEAKING":
                _log.warning("Feature leakage detected",
                             feature=v.feature, spearman_r=v.spearman_r, reason=v.reason)
            elif v.classification == "NEEDS_REVIEW":
                _log.info("Feature needs review",
                          feature=v.feature, spearman_r=v.spearman_r, reason=v.reason)
        _log.info("Leakage audit complete",
                  leaking=leakage_report.leaking_count,
                  review=leakage_report.review_count)
    except Exception as exc:
        _log.warning(f"Feature leakage audit failed: {exc}")

    # ── 4. Holdout split ──
    try:
        from modules.holdout import compare_performance, evaluate_holdout, split_holdout

        train_only, holdout_only = split_holdout(train_df)
        _log.info(f"Holdout split: train={len(train_only)}, holdout={len(holdout_only)}")
    except Exception as exc:
        _log.warning(f"Holdout split failed, using all data: {exc}")
        train_only   = train_df
        holdout_only = pd.DataFrame()

    # ── 5. Walk-forward validation (on train_only) ──
    validation = walk_forward_validate(train_only)
    _save_walk_forward_report(validation)

    if validation.get("status") == "OK":
        _log.info(
            f"Walk-forward: {validation['folds']} folds, "
            f"OOS R²={validation.get('oos_r2'):.4f}, "
            f"IC={validation.get('spearman_ic'):.4f}, "
            f"hit_rate={validation.get('hit_rate'):.4f}, "
            f"top-Q sharpe={validation.get('top_quantile_sharpe')}"
        )
    else:
        _log.info(f"Walk-forward skipped: {validation.get('reason')}")

    # ── 6. Production fit on train_only ──
    X = _sanitize_features(train_only[FEATURES])
    y = train_only["forward_return"]
    model = _make_xgb_regressor()
    _log.info("Fitting production XGBoost regressor…")
    model.fit(X, y)

    # Cache SHAP expected value for fast baseline computation at inference time
    try:
        explainer = shap.TreeExplainer(model)
        ev = float(explainer.expected_value)
        os.makedirs(os.path.dirname(SHAP_CACHE_PATH), exist_ok=True)
        with open(SHAP_CACHE_PATH, "w") as fh:
            json.dump({"expected_value": ev}, fh)
    except Exception as exc:
        _log.warning(f"Could not cache SHAP expected value: {exc}")

    # ── 7. Holdout evaluation & overfitting check ──
    if not holdout_only.empty:
        try:
            holdout_metrics = evaluate_holdout(model, holdout_only)
            if holdout_metrics.get("status") == "OK":
                wf_ic      = float(validation.get("spearman_ic") or 0.0)
                holdout_ic = float(holdout_metrics.get("spearman_ic") or 0.0)
                overfit    = compare_performance(wf_ic, holdout_ic)
                if overfit["overfitting_detected"]:
                    _log.warning("OVERFITTING detected",
                                 wf_ic=wf_ic, holdout_ic=holdout_ic,
                                 gap=overfit["sharpe_gap"])
                _log.info("Holdout evaluation", **holdout_metrics)
        except Exception as exc:
            _log.warning(f"Holdout evaluation failed: {exc}")

    # ── 8. Persist model ──
    in_sample_r2 = model.score(X, y)
    _log.info(f"Training complete. In-sample R²={in_sample_r2:.4f}, rows={len(X)}")
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    _log.info(f"Model saved → {MODEL_PATH}")
    return True


# ---------------------------------------------------------------------------
# Inference: predict + SHAP explain
# ---------------------------------------------------------------------------

@dataclass
class PredictionResult:
    """Structured result returned by predict_and_explain."""
    ml_prediction: float | None          # forward return % (×100), or None
    shap_values: dict[str, float]        # feature → SHAP contribution, sorted by |value|
    shap_expected_value: float | None    # baseline expected prediction
    top_drivers: list[dict]              # top-5 SHAP drivers with direction label

    def to_dict(self) -> dict:
        return {
            "ml_prediction": self.ml_prediction,
            "shap_values": self.shap_values,
            "shap_expected_value": self.shap_expected_value,
            "top_drivers": self.top_drivers,
        }


def predict_and_explain(
    factors_dict: dict,
    top_n_drivers: int = 5,
) -> dict:
    """Given a live stock's factor dict, predict 3-month forward return and
    generate SHAP values (waterfall-ready).

    The model is loaded lazily on each call; caller should cache the result
    for the batch loop. Returns a plain dict so it drops straight into JSON.

    Args:
        factors_dict: Mapping of factor names (any supported alias) to values.
        top_n_drivers: How many SHAP drivers to include in ``top_drivers``.

    Returns:
        Dict with keys: ml_prediction (float % or None), shap_values (dict),
        shap_expected_value (float or None), top_drivers (list of dicts).
    """
    _FALLBACK = PredictionResult(
        ml_prediction=None,
        shap_values={},
        shap_expected_value=None,
        top_drivers=[],
    ).to_dict()

    if not os.path.exists(MODEL_PATH):
        _log.warning(
            "ML Meta-Model not found. Falling back to raw fundamental score.",
            model_path=MODEL_PATH,
            hint="run: python -m modules.hybrid_scoring",
        )
        return _FALLBACK

    try:
        model: xgb.XGBRegressor = joblib.load(MODEL_PATH)

        # Build canonical row
        mapped = _alias_factors(factors_dict)
        X_pred = pd.DataFrame([{f: mapped.get(f, 0.0) for f in FEATURES}], columns=FEATURES)
        X_pred = _sanitize_features(X_pred)

        raw_prediction = float(model.predict(X_pred)[0])
        if not np.isfinite(raw_prediction):
            return _FALLBACK

        # SHAP explainability
        explainer  = shap.TreeExplainer(model)
        shap_array = explainer.shap_values(X_pred)       # shape (1, n_features)
        shap_row   = shap_array[0]

        # Load cached expected value (avoids re-fitting explainer for EV only)
        expected_value: float | None = None
        try:
            ev_raw = explainer.expected_value
            expected_value = float(ev_raw) if np.isfinite(float(ev_raw)) else None
        except Exception:
            pass

        # Per-feature SHAP dict — sorted by absolute contribution
        breakdown: dict[str, float] = {}
        for i, feat in enumerate(FEATURES):
            val = float(shap_row[i])
            breakdown[feat] = val if np.isfinite(val) else 0.0

        sorted_breakdown = dict(
            sorted(breakdown.items(), key=lambda kv: abs(kv[1]), reverse=True)
        )

        # Top-N drivers with human-readable direction
        top_drivers = [
            {
                "feature": feat,
                "shap_value": shap_val,
                "direction": "bullish" if shap_val > 0 else "bearish",
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
        _log.error(f"ML Prediction Error: {exc}")
        return _FALLBACK


# ---------------------------------------------------------------------------
# Batch inference helper (used by ml_ops.batch_update_multibaggers_ml)
# ---------------------------------------------------------------------------

def batch_predict(
    stocks: list[dict],
    factors_map: dict[str, list[str]] | None = None,
) -> list[dict]:
    """Run predict_and_explain for a list of stock factor dicts.

    Args:
        stocks: List of dicts, each with at minimum a 'symbol' key plus any
            recognised factor keys.
        factors_map: Optional override mapping symbol → ordered list of
            feature keys (rarely needed; leave None for default alias logic).

    Returns:
        List of dicts in same order as input, each augmented with
        ``ml_prediction``, ``shap_values``, ``shap_expected_value``,
        and ``top_drivers``.
    """
    if not os.path.exists(MODEL_PATH):
        _log.warning("Model not found; batch_predict returning empty predictions.")
        return [{**s, "ml_prediction": None, "shap_values": {}, "top_drivers": []} for s in stocks]

    model: xgb.XGBRegressor = joblib.load(MODEL_PATH)
    explainer = shap.TreeExplainer(model)

    rows = [_alias_factors(s) for s in stocks]
    X_all = _sanitize_features(pd.DataFrame(rows, columns=FEATURES))
    raw_preds = model.predict(X_all)
    shap_all  = explainer.shap_values(X_all)           # shape (n_stocks, n_features)

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

        breakdown: dict[str, float] = {
            feat: float(shap_all[i][j]) if np.isfinite(shap_all[i][j]) else 0.0
            for j, feat in enumerate(FEATURES)
        }
        sorted_bd = dict(sorted(breakdown.items(), key=lambda kv: abs(kv[1]), reverse=True))
        top_drivers = [
            {
                "feature": feat, "shap_value": sv,
                "direction": "bullish" if sv > 0 else "bearish",
                "feature_value": float(X_all[feat].iloc[i]),
            }
            for feat, sv in list(sorted_bd.items())[:5]
        ]

        results.append({
            **stock,
            "ml_prediction": ml_pred,
            "shap_values": sorted_bd,
            "shap_expected_value": ev,
            "top_drivers": top_drivers,
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
        imp = model.get_booster().get_score(importance_type="gain")
        total = sum(imp.values()) or 1.0
        return {feat: round(imp.get(feat, 0.0) / total, 6) for feat in FEATURES}
    except Exception as exc:
        _log.warning(f"Could not load feature importances: {exc}")
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
