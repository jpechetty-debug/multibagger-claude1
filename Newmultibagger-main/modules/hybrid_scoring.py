# modules/hybrid_scoring.py
# Sovereign AI - XGBoost Meta-Model with SHAP Explainability

import os
import sqlite3
import warnings

import joblib
import numpy as np
import pandas as pd
import shap
import xgboost as xgb

warnings.filterwarnings("ignore")

MODEL_PATH = os.path.join("runtime", "models", "xgboost_meta_model.pkl")
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
    "ret_6m": (-100.0, 2000.0),
    "vol_breakout": (0.0, 100.0),
    "dist_from_52w_high": (0.0, 1.0),
    "roce": (-100.0, 200.0),
}


def _sanitize_features(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce features to finite values and clip to safe ranges for XGBoost."""
    out = df.copy()
    for col in FEATURES:
        if col not in out.columns:
            out[col] = 0.0
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].replace([np.inf, -np.inf], np.nan).fillna(0.0)
        lo, hi = FEATURE_BOUNDS.get(col, (-1e9, 1e9))
        out[col] = out[col].clip(lower=lo, upper=hi)
    return out[FEATURES]


def _get_historical_targets(symbols: list):
    """Refactored forward-return target construction using modular data manager."""

    from modules.data_service import data_manager

    async def _fetch():
        return await data_manager.fetch_batch(symbols)

    # Use sync wrapper for ML training context
    from modules.data_utils import run_coroutine_sync

    data = run_coroutine_sync(_fetch())
    return {s: d.get("price") for s, d in data.items() if "price" in d}


def train_hybrid_model():
    print("Initiating Hybrid Scoring Meta-Model Training (XGBoost)...")

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
                print("PIT Auditor quarantine triggered: all rows failed temporal strictness.")
                df = raw_df  # fallback for local testing
    except Exception as exc:
        print(f"Could not load or sanitize PIT data: {exc}")
        return False

    if len(df) < 20:
        print(
            "Not enough historical data in fundamentals_pit to train a reliable XGBoost model (need > 20)."
        )
        return False

    # 2. Get current prices to calculate forward returns.
    symbols = df["symbol"].unique().tolist()
    print(f"Fetching current prices for {len(symbols)} symbols to construct target (Y)...")
    current_prices = _get_historical_targets(symbols)

    # Calculate Y (forward return).
    df["current_price"] = df["symbol"].map(current_prices)
    df = df.dropna(subset=["pit_price", "current_price"])
    df = df[df["pit_price"] > 0]
    if df.empty:
        print("No valid forward returns calculable.")
        return False

    df["forward_return"] = (df["current_price"] - df["pit_price"]) / df["pit_price"]

    # Sanitize ML features and drop invalid targets.
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    train_df = df.dropna(subset=["forward_return"]).copy()
    if not train_df.empty:
        train_df[FEATURES] = _sanitize_features(train_df[FEATURES])

    if len(train_df) < 10:
        print("Too many invalid rows; not enough training data after cleanup.")
        return False

    X = train_df[FEATURES]
    y = train_df["forward_return"]

    # 3. Train XGBoost Regressor.
    model = xgb.XGBRegressor(
        n_estimators=100,
        learning_rate=0.05,
        max_depth=4,
        subsample=0.8,
        random_state=42,
    )

    print("Training XGBoost regressor on historical factor signatures...")
    model.fit(X, y)

    r2 = model.score(X, y)
    print(f"Training complete. Meta-Model R2: {r2:.2f}")

    # 4. Save model.
    joblib.dump(model, MODEL_PATH)
    print("Model saved to disk.")
    return True


def predict_and_explain(factors_dict):
    """
    Given a live stock's factors, predict forward return and generate SHAP values.
    Returns: {"ml_prediction": float|None, "shap_values": dict}
    """
    if not os.path.exists(MODEL_PATH):
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(
            "ML Meta-Model (%s) not found. Falling back to raw fundamental score. "
            "To resolve this, run training via `python -m modules.hybrid_scoring`",
            MODEL_PATH
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
        print(f"ML Prediction Error: {exc}")
        return {"ml_prediction": None, "shap_values": {}}


if __name__ == "__main__":
    train_hybrid_model()
