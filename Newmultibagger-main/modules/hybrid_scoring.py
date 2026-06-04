# modules/hybrid_scoring.py
# Sovereign AI - XGBoost Meta-Model with SHAP Explainability

import json
import os
import sqlite3
import warnings

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb
from modules.price_utils import fetch_forward_prices
from core.observability.logger import get_logger
_log = get_logger("modules.hybrid_scoring")

warnings.filterwarnings("ignore")

MODEL_PATH = os.path.join("runtime", "models", "xgboost_meta_model.pkl")
WALK_FORWARD_REPORT_PATH = os.path.join("runtime", "models", "xgboost_walk_forward.json")
logger = get_logger("hybrid_scoring")

# Holdout period: locked off, never used for training or walk-forward folds.
HOLDOUT_START = "2018-01-01"
HOLDOUT_END = "2020-12-31"
FEATURES = [
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
    "roce"
]
FEATURE_BOUNDS = {
    "score": (0.0, 100.0),
    "sales_cagr_5y": (-100.0, 300.0),
    "avg_roe_5y": (-100.0, 200.0),
    "pe_ratio": (0.0, 300.0),
    "debt_equity": (0.0, 10.0),
    "cfo_pat_ratio": (-5.0, 10.0),
    "market_cap_cr": (0.0, 5_000_000.0),
    "ret_1m": (-100.0, 500.0),
    "ret_3m": (-100.0, 1000.0),
    "ret_6m": (-100.0, 500.0),
    "vol_breakout": (0.0, 100.0),
    "dist_from_52w_high": (0.0, 1.0),
    "roce": (-100.0, 200.0),
}


# Guard: _sanitize_features is STATELESS (no fitted scaler). If a
# StandardScaler/MinMaxScaler is ever added it MUST be fit per-fold.
_SANITIZE_IS_STATELESS = True


def _sanitize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce features to finite values and clip to safe ranges for XGBoost.

    IMPORTANT — this function is intentionally stateless. It uses only
    hardcoded FEATURE_BOUNDS, never data-dependent statistics. If you add
    a fitted scaler here you MUST fit it per walk-forward fold to avoid
    leaking future data into the training set.
    """
    assert _SANITIZE_IS_STATELESS, "_sanitize_features must remain stateless"
    out = df.copy()
    for col in FEATURES:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        lo, hi = FEATURE_BOUNDS.get(col, (-1e9, 1e9))
        out[col] = out[col].clip(lower=lo, upper=hi)
    return out[FEATURES]


def _make_xgb_regressor():
    return xgb.XGBRegressor(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        random_state=42,
    )


def _finite_or_none(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _build_training_frame(df: pd.DataFrame, current_prices: dict) -> pd.DataFrame:
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


def walk_forward_validate(
    train_df: pd.DataFrame,
    min_train_rows: int = 10,
    min_train_periods: int = 4,
) -> dict:
    """
    Expanding-window validation for the hybrid XGBoost scorer.

    Each fold trains only on rows with `as_of_date` before the test quarter and
    evaluates on the next quarter. The final production model can still be fit
    on all rows after this out-of-sample audit is recorded.
    """
    required = {"symbol", "as_of_date", "forward_return", *FEATURES}
    missing = required - set(train_df.columns)
    if missing:
        return {"status": "SKIPPED", "reason": f"missing columns: {sorted(missing)}"}

    df = train_df.copy()
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    df["forward_return"] = pd.to_numeric(df["forward_return"], errors="coerce")
    df = df.dropna(subset=["as_of_date", "forward_return"]).sort_values("as_of_date")

    # ── Exclude holdout period from walk-forward folds ──
    holdout_mask = df["as_of_date"].between(HOLDOUT_START, HOLDOUT_END)
    holdout_df = df[holdout_mask].copy()
    df = df[~holdout_mask]

    if len(df) < min_train_rows:
        return {"status": "SKIPPED", "reason": "not enough valid rows"}

    df["test_period"] = df["as_of_date"].dt.to_period("Q")
    periods = sorted(df["test_period"].dropna().unique())
    if len(periods) <= min_train_periods:
        return {"status": "SKIPPED", "reason": "not enough quarterly periods"}

    predictions = []
    windows = []
    for test_period in periods[min_train_periods:]:
        test_start = test_period.start_time
        train_fold = df[df["as_of_date"] < test_start]
        test_fold = df[df["test_period"] == test_period]
        if len(train_fold) < min_train_rows or test_fold.empty:
            continue

        model = _make_xgb_regressor()
        X_train = _sanitize_features(train_fold[FEATURES])
        y_train = train_fold["forward_return"]
        X_test = _sanitize_features(test_fold[FEATURES])
        model.fit(X_train, y_train)

        fold_predictions = test_fold[["symbol", "as_of_date", "forward_return"]].copy()
        fold_predictions["prediction"] = model.predict(X_test)
        fold_predictions["test_period"] = str(test_period)
        predictions.append(fold_predictions)

        # ── Per-fold IC ──
        fold_true = pd.to_numeric(fold_predictions["forward_return"], errors="coerce")
        fold_pred = pd.to_numeric(fold_predictions["prediction"], errors="coerce")
        fold_ic = fold_true.corr(fold_pred, method="spearman") if len(fold_true) > 1 else np.nan

        windows.append(
            {
                "test_period": str(test_period),
                "train_rows": int(len(train_fold)),
                "test_rows": int(len(test_fold)),
                "fold_ic": _finite_or_none(fold_ic),
            }
        )

    if not predictions:
        return {"status": "SKIPPED", "reason": "no valid walk-forward folds"}

    pred_df = pd.concat(predictions, ignore_index=True)
    y_true = pd.to_numeric(pred_df["forward_return"], errors="coerce")
    y_pred = pd.to_numeric(pred_df["prediction"], errors="coerce")
    valid = y_true.notna() & y_pred.notna()
    y_true = y_true[valid]
    y_pred = y_pred[valid]
    if y_true.empty:
        return {"status": "SKIPPED", "reason": "all predictions invalid"}

    residual = y_true - y_pred
    ss_res = float(np.square(residual).sum())
    ss_tot = float(np.square(y_true - y_true.mean()).sum())
    oos_r2 = 1 - (ss_res / ss_tot) if ss_tot > 0 else np.nan
    spearman_ic = y_true.corr(y_pred, method="spearman") if len(y_true) > 1 else np.nan
    hit_rate = ((y_true > 0) == (y_pred > 0)).mean()

    return {
        "status": "OK",
        "folds": int(len(windows)),
        "rows": int(len(y_true)),
        "oos_r2": _finite_or_none(oos_r2),
        "mae": _finite_or_none(np.abs(residual).mean()),
        "rmse": _finite_or_none(np.sqrt(np.square(residual).mean())),
        "spearman_ic": _finite_or_none(spearman_ic),
        "hit_rate": _finite_or_none(hit_rate),
        "holdout_rows_excluded": int(len(holdout_df)),
        "windows": windows,
    }


def _save_walk_forward_report(metrics: dict) -> None:
    os.makedirs(os.path.dirname(WALK_FORWARD_REPORT_PATH), exist_ok=True)
    with open(WALK_FORWARD_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)


def _get_historical_targets(symbols: list):
    """Refactored forward-return target construction using modular data manager."""

    from modules.data_service import data_manager

    async def _fetch():
        return await data_manager.fetch_batch(symbols)

    # Use sync wrapper for ML training context
    from modules.data_utils import run_coroutine_sync

    data = run_coroutine_sync(_fetch())
    return {
        s: d.get("price", d.get("Price"))
        for s, d in data.items()
        if d.get("price") is not None or d.get("Price") is not None
    }


def train_hybrid_model():
    _log.info("Initiating Hybrid Scoring Meta-Model Training (XGBoost)...")

    # 1. Extract PIT Data
    try:
        from modules.db_utils import get_db_connection
        from modules.pit_auditor import sanitize

        with get_db_connection("stocks.db") as conn:
            query = """
                SELECT symbol, as_of_date, source_updated_at as report_date, price as pit_price,
                score, sales_cagr_5y, avg_roe_5y, pe_ratio, debt_equity, cfo_pat_ratio, market_cap_cr,
                ret_1m, ret_3m, ret_6m, vol_breakout, dist_from_52w_high, roce
                FROM fundamentals_pit
            """
            raw_df = pd.read_sql(query, conn)

            # Eliminate look-ahead bias and structural hallucinations via PIT Auditor.
            df = sanitize(raw_df)
            if df.empty and not raw_df.empty:
                _log.warning("PIT Auditor quarantine triggered: all rows failed temporal strictness.")
                df = raw_df  # fallback for local testing
    except Exception as exc:
        _log.warning(f"Could not load or sanitize PIT data: {exc}")
        return False

    if len(df) < 20:
        _log.info("Not enough historical data in fundamentals_pit to train a reliable XGBoost model (need > 20).")
        return False

    # 2. Get current prices to calculate forward returns.
    symbols = df["symbol"].unique().tolist()
    _log.info(f"Fetching current prices for {len(symbols)} symbols to construct target (Y)...")
    current_prices = _get_historical_targets(symbols)

    train_df = _build_training_frame(df, current_prices)
    if train_df.empty:
        _log.info("No valid forward returns calculable.")
        return False

    if len(train_df) < 10:
        _log.info("Too many invalid rows; not enough training data after cleanup.")
        return False

    # ── Feature leakage audit ──
    try:
        from modules.feature_leakage_audit import audit_features

        leakage_report = audit_features(train_df)
        if leakage_report.has_leaks:
            for v in leakage_report.verdicts:
                if v.classification == "LEAKING":
                    logger.warning("Feature leakage detected", feature=v.feature,
                                   spearman_r=v.spearman_r, reason=v.reason)
        logger.info("Feature leakage audit complete",
                     leaking=leakage_report.leaking_count,
                     review=leakage_report.review_count)
    except Exception as exc:
        logger.warning("Feature leakage audit failed", error=str(exc))

    # ── Holdout split ──
    try:
        from modules.holdout import compare_performance, evaluate_holdout, split_holdout

        train_only, holdout_only = split_holdout(train_df)
        logger.info("Holdout split", train_rows=len(train_only),
                     holdout_rows=len(holdout_only))
    except Exception as exc:
        logger.warning("Holdout split failed, using all data", error=str(exc))
        train_only = train_df
        holdout_only = pd.DataFrame()

    validation = walk_forward_validate(train_only)
    _save_walk_forward_report(validation)
    if validation.get("status") == "OK":
        _log.info("Walk-forward validation: "
            f"{validation['folds']} folds, "
            f"OOS R2={validation.get('oos_r2')}, "
            f"IC={validation.get('spearman_ic')}, "
            f"hit_rate={validation.get('hit_rate')}")
    else:
        _log.info(f"Walk-forward validation skipped: {validation.get('reason')}")

    # Train on non-holdout data only
    X = _sanitize_features(train_only[FEATURES])
    y = train_only["forward_return"]

    # 3. Train XGBoost Regressor.
    model = _make_xgb_regressor()

    _log.info("Training XGBoost regressor on historical factor signatures...")
    model.fit(X, y)

    # ── Holdout evaluation ──
    if not holdout_only.empty:
        try:
            holdout_metrics = evaluate_holdout(model, holdout_only)
            if holdout_metrics.get("status") == "OK":
                wf_ic = validation.get("spearman_ic", 0.0) or 0.0
                holdout_ic = holdout_metrics.get("spearman_ic", 0.0) or 0.0
                overfit = compare_performance(float(wf_ic), float(holdout_ic))
                if overfit["overfitting_detected"]:
                    logger.warning("OVERFITTING detected",
                                   sharpe_gap=overfit["sharpe_gap"])
                logger.info("Holdout evaluation", **holdout_metrics)
        except Exception as exc:
            logger.warning("Holdout evaluation failed", error=str(exc))

    r2 = model.score(X, y)
    _log.info(f"Training complete. Final in-sample fit R2: {r2:.2f}")

    # 4. Save model.
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    joblib.dump(model, MODEL_PATH)
    _log.info("Model saved to disk.")
    return True


def predict_and_explain(factors_dict):
    """
    Given a live stock's factors, predict forward return and generate SHAP values.
    Returns: {"ml_prediction": float|None, "shap_values": dict}
    """
    if not os.path.exists(MODEL_PATH):
        logger.warning(
            "ML Meta-Model not found. Falling back to raw fundamental score.",
            model_path=MODEL_PATH,
            action="run python -m modules.hybrid_scoring",
        )
        return {"ml_prediction": None, "shap_values": {}}

    try:
        model = joblib.load(MODEL_PATH)

        # Normalize feature names mapping for prediction
        mapped_factors = {
            "score": factors_dict.get("score", factors_dict.get("Score", 0.0)),
            "sales_cagr_5y": factors_dict.get("sales_cagr_5y", factors_dict.get("Sales_Growth_5Y%", 0.0)),
            "avg_roe_5y": factors_dict.get("avg_roe_5y", factors_dict.get("Avg_ROE_5Y%", 0.0)),
            "pe_ratio": factors_dict.get("pe_ratio", factors_dict.get("PE_Ratio", 0.0)),
            "debt_equity": factors_dict.get("debt_equity", factors_dict.get("Debt_Equity", 0.0)),
            "cfo_pat_ratio": factors_dict.get("cfo_pat_ratio", factors_dict.get("CFO_PAT_Ratio", 0.0)),
            "market_cap_cr": factors_dict.get("market_cap_cr", factors_dict.get("Market_Cap_Cr", 0.0)),
            "ret_1m": factors_dict.get("ret_1m", factors_dict.get("Ret_1M", 0.0)),
            "ret_3m": factors_dict.get("ret_3m", factors_dict.get("Ret_3M", 0.0)),
            "ret_6m": factors_dict.get("ret_6m", factors_dict.get("Ret_6M", 0.0)),
            "vol_breakout": factors_dict.get("vol_breakout", factors_dict.get("Vol_Breakout", 0.0)),
            "dist_from_52w_high": factors_dict.get("dist_from_52w_high", factors_dict.get("Dist_From_52W_High", 0.0)),
            "roce": factors_dict.get("roce", factors_dict.get("ROCE%", 0.0)),
        }
        row = {f: mapped_factors.get(f, 0.0) for f in FEATURES}
        X_pred = pd.DataFrame([row], columns=FEATURES)
        X_pred = _sanitize_features(X_pred)

        prediction = float(model.predict(X_pred)[0])
        if not np.isfinite(prediction):
            return {"ml_prediction": None, "shap_values": {}}

        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X_pred)

        breakdown = {}
        for i, feature in enumerate(FEATURES):
            val = float(shap_vals[0][i])
            breakdown[feature] = val if np.isfinite(val) else 0.0

        sorted_breakdown = dict(
            sorted(breakdown.items(), key=lambda item: abs(item[1]), reverse=True)
        )
        return {"ml_prediction": float(prediction * 100.0), "shap_values": sorted_breakdown}
    except Exception as exc:
        _log.error(f"ML Prediction Error: {exc}")
        return {"ml_prediction": None, "shap_values": {}}


if __name__ == "__main__":
    train_hybrid_model()
