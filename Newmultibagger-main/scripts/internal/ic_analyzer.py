import os
import sys

# Ensure root directory is in path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import sqlite3
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from modules.connections import DB_PATH
from modules.hybrid_scoring import FEATURES

import yfinance as yf

def fetch_forward_prices(df_input, months=3):
    """Fetch forward prices using yfinance monthly data."""
    df = df_input.copy()
    symbols = df["symbol"].unique().tolist()
    print(f"Fetching monthly history for {len(symbols)} symbols...")

    hist_dfs = []
    chunk_size = 200
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i+chunk_size]
        try:
            h = yf.download(chunk, period="10y", interval="1mo", progress=False)
            if not h.empty:
                if isinstance(h.columns, pd.MultiIndex):
                    if "Close" in h.columns:
                        hist_dfs.append(h["Close"])
                else:
                    if "Close" in h:
                        hist_dfs.append(pd.DataFrame({chunk[0]: h["Close"]}))
        except Exception as e:
            print(f"Error fetching chunk: {e}")

    if not hist_dfs:
        return pd.Series(dtype=float)

    # Join chunks avoiding duplicate columns
    close_prices = pd.concat(hist_dfs, axis=1)
    close_prices = close_prices.loc[:,~close_prices.columns.duplicated()]

    if close_prices.index.tz is not None:
        close_prices.index = close_prices.index.tz_convert(None)

    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    df["target_date"] = df["as_of_date"] + pd.DateOffset(months=months)

    def get_forward_price(row):
        sym = row["symbol"]
        t_date = row["target_date"]
        if sym not in close_prices.columns:
            return np.nan

        sym_prices = close_prices[sym].dropna()
        if sym_prices.empty:
            return np.nan

        # Find closest date >= target_date
        future_prices = sym_prices[sym_prices.index >= t_date]
        if future_prices.empty:
            return np.nan

        closest_date = future_prices.index[0]
        if (closest_date - t_date).days <= 35:
            return future_prices.iloc[0]
        return np.nan

    return df.apply(get_forward_price, axis=1)

def perform_ic_analysis():
    print("=" * 60)
    print(" Information Coefficient (IC) Analysis for Factor Validation")
    print("=" * 60)

    try:
        conn = sqlite3.connect(DB_PATH)
        existing = pd.read_sql("PRAGMA table_info(fundamentals_pit)", conn)["name"].tolist()
        safe_features = [f for f in FEATURES if f in existing]
        query = f"""
            SELECT symbol, as_of_date, price as pit_price, score, {', '.join(safe_features)}
            FROM fundamentals_pit
            WHERE sector != 'DELISTED'
        """
        df = pd.read_sql(query, conn)
        conn.close()
    except Exception as e:
        print(f"Failed to fetch PIT data: {e}")
        return

    if df.empty:
        print("No data available in fundamentals_pit for analysis.")
        return

    print(f"Loaded {len(df)} historical PIT records.")

    df["forward_price"] = fetch_forward_prices(df, months=3)
    df = df.dropna(subset=["pit_price", "forward_price"])
    df = df[df["pit_price"] > 0]

    if df.empty:
        print("No valid forward returns calculable (missing future prices).")
        return

    # Calculate 3-Month Forward Return
    df["forward_return"] = (df["forward_price"] - df["pit_price"]) / df["pit_price"]

    # Handle synthetic delisted records explicitly
    df.loc[df["forward_return"] < -0.99, "forward_return"] = -1.0

    print(f"\nAnalyzing {len(df)} records with valid forward returns.")
    print("-" * 60)
    print(f"{'Factor':<25} | {'IC (Spearman)':<15} | {'p-value':<15}")
    print("-" * 60)

    factors_to_test = ["score"] + FEATURES
    ic_results = []

    for factor in factors_to_test:
        if factor not in df.columns:
            continue

        # Clean data for correlation
        clean_df = df.dropna(subset=[factor, "forward_return"])
        if len(clean_df) < 10:
            continue

        res = spearmanr(clean_df[factor], clean_df["forward_return"])

        # Handle different SciPy versions (tuple vs SignificanceResult)
        if hasattr(res, 'statistic'):
            correlation = res.statistic
            p_value = res.pvalue
        else:
            correlation = res[0]
            p_value = res[1]

        ic_results.append({
            "Factor": factor,
            "IC": float(correlation) if isinstance(correlation, (int, float, np.floating)) else 0.0,
            "p_value": float(p_value) if isinstance(p_value, (int, float, np.floating)) else 1.0
        })

    # Sort by absolute IC (predictive power)
    ic_results.sort(key=lambda x: abs(x["IC"]) if not np.isnan(x["IC"]) else 0, reverse=True)

    for res in ic_results:
        factor = res["Factor"]
        ic = res["IC"]
        p_val = res["p_value"]

        # Format
        ic_str = f"{ic:.4f}" if not np.isnan(ic) else "NaN"
        p_str = f"{p_val:.4f}" if not np.isnan(p_val) else "NaN"

        # Highlight significant factors (p < 0.05) and strong IC (|IC| > 0.05)
        marker = ""
        if not np.isnan(p_val) and p_val < 0.05:
            if abs(ic) > 0.05:
                marker = "***"
            else:
                marker = "*"

        print(f"{factor:<25} | {ic_str:<15} | {p_str:<10} {marker}")

    print("-" * 60)
    print(" *** indicates statistically significant with high predictive power (|IC| > 0.05, p < 0.05)")
    print(" *   indicates statistically significant but weak predictive power (p < 0.05)")
    print("\nUse these results to adjust factor weights in config.py (SCORING_WEIGHTS).")

if __name__ == "__main__":
    perform_ic_analysis()
