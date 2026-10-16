#!/usr/bin/env python3
"""
Sovereign Terminal — Share Price & Valuation Scanner.
Scans and updates market prices, 52W range, Graham Value Gap, and trade setup
using official NSE UDiFF Bhavcopy and live feed fallbacks.

Usage:
    python scripts/internal/scan_shares.py
    python scripts/internal/scan_shares.py --symbols INFY.NS,RELIANCE.NS
"""

import argparse
import io
import os
import sqlite3
import sys
from datetime import date, datetime

import pandas as pd

# UTF-8 wrapping for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

from db.db_core import DB_PATH
import db.repository as database
from modules.adapters.nse_bhavcopy import download_bhavcopy, get_bhavcopy_price


def scan_and_update_prices(target_symbols: list[str] | None = None) -> int:
    """Scan and update share prices in stocks.db multibaggers table."""
    print("=" * 65)
    print("🚀 MULTIBAGGER SHARE PRICE SCANNER")
    print("=" * 65)

    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return 0

    conn = sqlite3.connect(DB_PATH)
    df_db = pd.read_sql("SELECT * FROM multibaggers", conn)
    conn.close()

    if df_db.empty:
        print("❌ No records found in multibaggers table.")
        return 0

    print(f"Loaded {len(df_db)} stocks from database.")

    # Reverse map column names to repository contract
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

    if target_symbols:
        target_set = {s.strip().upper() for s in target_symbols}
        # Add variants with and without .NS
        expanded_targets = set(target_set)
        for s in target_set:
            if s.endswith(".NS"):
                expanded_targets.add(s[:-3])
            else:
                expanded_targets.add(f"{s}.NS")
        mask = df["Symbol"].str.upper().isin(expanded_targets)
        target_df = df[mask]
        print(f"Filtering to {len(target_df)} requested target symbols.")
    else:
        target_df = df

    print("Fetching today's NSE Bhavcopy...")
    bhavcopy_prices = download_bhavcopy()
    print(f"Loaded {len(bhavcopy_prices)} quotes from official NSE Bhavcopy.")

    import yfinance as yf

    updated_count = 0
    price_changed_count = 0

    for idx in target_df.index:
        sym = str(df.at[idx, "Symbol"]).strip()
        if not sym:
            continue

        clean_sym = sym.replace(".NS", "").replace(".BO", "")
        new_price = get_bhavcopy_price(bhavcopy_prices, sym) or get_bhavcopy_price(bhavcopy_prices, clean_sym)

        # Fallback to yfinance if not in Bhavcopy (e.g. BSE ticker)
        if new_price is None or new_price <= 0:
            try:
                hist = yf.Ticker(sym).history(period="2d")
                if not hist.empty and "Close" in hist.columns:
                    val = float(hist["Close"].iloc[-1])
                    if val > 0:
                        new_price = val
            except Exception:
                pass

        if new_price and new_price > 0:
            new_price = round(float(new_price), 2)
            old_price = float(df.at[idx, "Price"] or 0.0)

            if abs(new_price - old_price) > 0.01:
                price_changed_count += 1

            df.at[idx, "Price"] = new_price
            updated_count += 1

            # Recalculate 52W range metrics
            high_52w = float(df.at[idx, "High_52W"] or 0.0)
            if new_price > high_52w:
                high_52w = new_price
                df.at[idx, "High_52W"] = round(high_52w, 2)
            if high_52w > 0:
                down_pct = round(((high_52w - new_price) / high_52w) * 100, 2)
                df.at[idx, "Down_From_52W_High%"] = down_pct
                df.at[idx, "Dist_From_52W_High"] = round((high_52w - new_price) / high_52w, 4)

            low_52w = float(df.at[idx, "Low_52W"] or 0.0)
            if low_52w <= 0 or new_price < low_52w:
                df.at[idx, "Low_52W"] = round(new_price, 2)

            # Recalculate Graham Number & Value Gap
            graham_num = float(df.at[idx, "Graham_Number"] or 0.0)
            if graham_num > 0 and new_price > 0:
                df.at[idx, "Value_Gap%"] = round(((graham_num - new_price) / new_price) * 100, 2)

            # Recalculate Trade Setup Risk Parameters
            atr = float(df.at[idx, "ATR"] or 0.0)
            if atr <= 0:
                atr = round(new_price * 0.02, 2)
                df.at[idx, "ATR"] = atr
            df.at[idx, "Buy_Below"] = round(new_price * 1.02, 2)
            df.at[idx, "Stop_Loss"] = round(max(0.1, new_price - 2 * atr), 2)
            df.at[idx, "Stop_Loss_ATR"] = round(max(0.1, new_price - 2 * atr), 2)
            df.at[idx, "Target_1"] = round(new_price + 3 * atr, 2)
            df.at[idx, "Max_Qty_1L"] = int(100000 / new_price) if new_price > 0 else 0

            # Adjust Market Cap and P/E based on price movement
            if old_price > 0 and new_price > 0:
                ratio = new_price / old_price
                mcap = float(df.at[idx, "Market_Cap_Cr"] or 0.0)
                if mcap > 0:
                    df.at[idx, "Market_Cap_Cr"] = round(mcap * ratio, 2)
                pe = float(df.at[idx, "PE_Ratio"] or 0.0)
                if pe > 0:
                    df.at[idx, "PE_Ratio"] = round(pe * ratio, 2)

    today_str = date.today().isoformat()
    df["As_Of_Date"] = today_str
    df["updated_at"] = datetime.now()

    # Save to SQLite and CSV
    print(f"\nPersisting {len(df)} stocks to SQLite...")
    database.save_multibaggers(df, replace_existing=True)

    csv_path = os.path.join(PROJECT_ROOT, "screener_results.csv")
    df.to_csv(csv_path, index=False)
    print(f"Saved screener results to {csv_path}")

    print("\n" + "=" * 65)
    print(f"✅ SCAN COMPLETE: {updated_count} shares scanned.")
    print(f"📊 Prices updated/corrected for: {price_changed_count} shares.")
    print("=" * 65)

    return updated_count


def main():
    parser = argparse.ArgumentParser(description="Scan and refresh share prices")
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols to refresh (e.g. INFY.NS,RELIANCE.NS)",
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    scan_and_update_prices(symbols)


if __name__ == "__main__":
    main()
