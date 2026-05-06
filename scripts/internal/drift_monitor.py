import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

# Ensure modules can be imported
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.connections import DB_PATH


def run_drift_monitor() -> None:
    print("🛰️ Initiating Real-Time Drift Monitor (Phase 55)...")

    # 1. System Health Check
    if not os.path.exists(DB_PATH):
        print(f"❌ CRITICAL: Database Missing at {DB_PATH}!")
        return

    # Check DB Data Freshness
    mod_time = os.path.getmtime(DB_PATH)
    age_hours = (time.time() - mod_time) / 3600

    print(f"⏱️ System Age: {age_hours:.1f} hours")

    if age_hours > 24:
        print("⚠️ WARNING: Data Stale (> 24h). Run screener.py immediately.")
    else:
        print("✅ Data Fresh.")

    # 2. Market Drift Check (Correlation)
    # Check if the "Multibagger" Universe is correlating with Nifty.
    # If correlation drops, it means "Regime decoupling" (Good or Bad).

    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql(
            "SELECT symbol, price, rs_rating FROM multibaggers ORDER BY rs_rating DESC LIMIT 10",
            conn,
        )
        conn.close()

        if df.empty:
            print("⚠️ DB Empty.")
            return

        print("📊 Analyzing Top 10 Stocks vs Nifty 50...")
        top_tickers = df["symbol"].tolist()

        # Download Data
        data = yf.download(top_tickers + ["^NSEI"], period="1mo", progress=False)["Close"]
        
        # Forward fill and drop any completely missing columns
        data = data.ffill().dropna(axis=1, how="all")

        # Correlation
        if "^NSEI" not in data.columns:
            print("⚠️ ^NSEI data missing, cannot compute correlation.")
            return

        nifty = data["^NSEI"]
        correlations: list[float] = []

        for sym in top_tickers:
            if sym in data.columns:
                corr = data[sym].corr(nifty)
                if pd.notna(corr):
                    correlations.append(float(corr))

        avg_corr = sum(correlations) / len(correlations) if correlations else 0.0

        print(f"🔗 Portfolio-Nifty Correlation (1 Month): {avg_corr:.2f}")

        if avg_corr < 0.3:
            print("📢 DRIFT ALERT: Portfolio Decoupled from Nifty. (Alpha Mode)")
        elif avg_corr > 0.8:
            print("📢 DRIFT ALERT: Portfolio Tracking Index. (Beta Mode)")
        else:
            print("✅ Portfolio behaving normally (Hybrid Correlation).")

        # Save Report (Log)
        runtime_dir = PROJECT_ROOT / "runtime"
        runtime_dir.mkdir(exist_ok=True)
        
        with open(runtime_dir / "drift_log.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.ctime()} | Age: {age_hours:.1f}h | Correlation: {avg_corr:.2f}\n")

        json_output = {
            "timestamp": pd.Timestamp.now().isoformat(),
            "age_hours": round(age_hours, 1),
            "correlation": round(avg_corr, 2),
            "status": "DECOUPLED" if avg_corr < 0.3 else "TRACKING" if avg_corr > 0.8 else "NORMAL",
            "data_fresh": age_hours < 24,
        }
        with open(runtime_dir / "drift.json", "w") as f:
            json.dump(json_output, f, indent=4)

        print(f"📄 Drift metrics saved to {runtime_dir / 'drift.json'}")

    except Exception as e:
        print(f"❌ Monitor Error: {e}")


if __name__ == "__main__":
    run_drift_monitor()
