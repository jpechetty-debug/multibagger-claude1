import os
import sys
import pandas as pd
import sqlite3
from datetime import datetime, date

# UTF-8 wrapping for Windows stdout/stderr to support emojis
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Ensure root directory is in path for imports
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

print("Starting simulated recan for universe...")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Simulated recan for universe")
    parser.add_argument("--confirm", action="store_true", help="Confirm execution to allow database updates")
    parser.add_argument("--date", type=str, default=None, help="A specific As_Of_Date to use (defaults to today)")
    args = parser.parse_args()

    if not args.confirm:
        print("❌ Error: Running this script with replace_existing=True will overwrite the entire multibaggers table.")
        print("💡 Please run this script with the --confirm flag to acknowledge and proceed:")
        print("   python scripts/internal/recan_universe.py --confirm")
        sys.exit(1)

    db_path = os.path.join(PROJECT_ROOT, "runtime", "stocks.db")
    if not os.path.exists(db_path):
        print(f"❌ Database not found at {db_path}")
        return

    # 1. Read existing multibaggers from DB
    conn = sqlite3.connect(db_path)
    df_db = pd.read_sql("SELECT * FROM multibaggers", conn)
    conn.close()

    if df_db.empty:
        print("❌ No records found in multibaggers table.")
        return

    print(f"Loaded {len(df_db)} records from multibaggers.")

    # 2. Reverse map columns back to DataFrame names for save_multibaggers
    mapping = {
        "Symbol": "symbol",
        "Price": "price",
        "Sector": "sector",
        "Score": "score",
        "F_Score": "f_score",
        "F_Score_Max": "f_score_max",
        "Rating": "rating",
        "Buy_Below": "buy_below",
        "Stop_Loss": "stop_loss",
        "Target_1": "target_1",
        "Sales_Growth_TTM%": "sales_growth",
        "ROE%": "roe",
        "PEG_Ratio": "peg_ratio",
        "Debt_Equity": "debt_equity",
        "RSI": "rsi",
        "Smart_Money%": "smart_money",
        "Market_Cap_Cr": "market_cap_cr",
        "CFO_PAT_Ratio": "cfo_pat_ratio",
        "Sales_Growth_5Y%": "sales_cagr_5y",
        "Avg_ROE_5Y%": "avg_roe_5y",
        "PE_Ratio": "pe_ratio",
        "Down_From_52W_High%": "down_from_52w",
        "RS_Rating": "rs_rating",
        "Earnings_Accel": "earnings_accel",
        "Sector_Leader": "sector_leader",
        "Graham_Number": "graham_number",
        "Value_Gap%": "value_gap",
        "Technical_Signal": "technical_signal",
        "Analyst_Rating": "analyst_rating",
        "Analyst_Upside%": "analyst_upside",
        "Promoter_Holding%": "promoter_holding",
        "Inst_Holding%": "inst_holding",
        "ATR": "atr",
        "Stop_Loss_ATR": "stop_loss_atr",
        "Max_Qty_1L": "max_qty_1l",
        "As_Of_Date": "as_of_date",
        "updated_at": "updated_at",
        "Conviction_Score": "conviction_score",
        "Conviction_Boost": "conviction_boost",
        "Institutional_Interest": "institutional_interest",
        "Super_Investors": "super_investors",
        "Data_Quality": "data_quality",
        "Data_Confidence": "data_confidence",
        "F_Score_Method": "f_score_method",
        "Backtest_CAGR": "backtest_cagr",
        "Backtest_Win_Rate": "backtest_win_rate",
        "Backtest_Max_DD": "backtest_max_dd",
        "Backtest_Sharpe": "backtest_sharpe",
        "ML_Predicted_Return": "ml_predicted_return",
        "SHAP_Breakdown": "shap_breakdown",
        "High_52W": "high_52w",
        "Low_52W": "low_52w",
        "Pledge_Pct": "pledge_pct",
        "Piotroski_Score": "piotroski_score",
        "ROCE_pct": "roce",
        "Median_PAT_Growth_5Y_pct": "median_pat_growth",
        "ml_rank_score": "ml_rank_score",
        "Ret_1M": "ret_1m",
        "Ret_3M": "ret_3m",
        "Ret_6M": "ret_6m",
        "Vol_Breakout": "vol_breakout",
        "Dist_From_52W_High": "dist_from_52w_high",
        "Revenue_CAGR_3Y": "revenue_cagr_3y",
        "Revenue_CAGR_5Y": "revenue_cagr_5y",
        "PAT_CAGR_3Y": "pat_cagr_3y",
        "PAT_CAGR_5Y": "pat_cagr_5y",
        "EPS_CAGR_3Y": "eps_cagr_3y",
        "EPS_CAGR_5Y": "eps_cagr_5y",
        "CAGR_Consistency": "cagr_consistency",
        "Dividend_Yield": "dividend_yield",
        "Dividend_Payout": "dividend_payout",
        "Cap_Category": "cap_category",
        "Data_Quality_Flags": "data_quality_flags",
    }

    reverse_mapping = {v: k for k, v in mapping.items()}
    df = df_db.rename(columns=reverse_mapping)

    # 3. Set the date and timestamp dynamically (or from CLI override)
    target_date = args.date or date.today().isoformat()
    df["As_Of_Date"] = target_date
    df["updated_at"] = datetime.now()

    print(f"Updated dates to {target_date}.")

    # 4. Save to CSV (expected by backtest_picks)
    csv_path = os.path.join(PROJECT_ROOT, "screener_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"Saved screener results to {csv_path}")

    # 5. Call save_multibaggers to update DB and fundamentals_pit
    print("Saving multibaggers to DB...")
    import db.repository as database
    database.save_multibaggers(df, replace_existing=True)
    print("✅ Saved to database successfully.")

    # 6. Run Institutional Analysis Pipeline
    print("\n" + "=" * 50)
    print("  RUNNING INSTITUTIONAL ANALYSIS PIPELINE")
    print("=" * 50)

    # Add scripts/internal to sys.path so we can import modules from it
    scripts_internal_path = os.path.join(PROJECT_ROOT, "scripts", "internal")
    sys.path.insert(0, scripts_internal_path)
import modules.adapters.yf_patch  # noqa: F401

    # 1. Backtest Picks
    try:
        import backtest_picks
        print("Running Backtest Picks...")
        backtest_picks.backtest_picks()
        print("✅ Backtest Picks complete.")
    except Exception as e:
        print(f"❌ Backtest Picks Error: {e}")

    # 2. Alpha Attribution
    try:
        import alpha_attribution
        print("Running Alpha Attribution...")
        alpha_attribution.run_attribution()
        print("✅ Alpha Attribution complete.")
    except Exception as e:
        print(f"❌ Alpha Attribution Error: {e}")

    # 3. Liquidity Stress Test
    try:
        import liquidity_simulator
        print("Running Liquidity Check...")
        liquidity_simulator.run_liquidity_check()
        print("✅ Liquidity Check complete.")
    except Exception as e:
        print(f"❌ Liquidity Check Error: {e}")

    # 4. Walk-Forward Validation
    try:
        import backtest_engine
        print("Running Backtest Engine...")
        backtest_engine.run_backtest()
        print("✅ Backtest Engine complete.")
    except Exception as e:
        print(f"❌ Backtest Engine Error: {e}")

    print("\n🎉 Recan and analysis pipeline complete.")

if __name__ == "__main__":
    main()
