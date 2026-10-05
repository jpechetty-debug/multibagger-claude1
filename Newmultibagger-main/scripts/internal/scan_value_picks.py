#!/usr/bin/env python3
"""
Sovereign Terminal — Comprehensive Value Universe & Metrics Scanner.
Scans and recalculates intrinsic valuation, Graham Number, Value Gap%,
PE/PEG ratios, Piotroski scores, and trade setup across all value stocks
using official NSE Bhavcopy and fundamental data layers.

Usage:
    python scripts/internal/scan_value_picks.py --all
    python scripts/internal/scan_value_picks.py --symbols COALINDIA.NS,ONGC.NS
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import io
import os
from pathlib import Path
import sqlite3
import sys

# UTF-8 wrapping for Windows stdout/stderr
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from db.db_core import DB_PATH
import db.repository as database
from modules.adapters.nse_bhavcopy import download_bhavcopy
import modules.adapters.yf_patch  # noqa: F401
from modules.data_layer.data_service import DataManager
import screener

# Core Deep-Value & Graham Formula Universe
DEEP_VALUE_UNIVERSE = [
    "COALINDIA.NS",
    "ONGC.NS",
    "POWERGRID.NS",
    "HEROMOTOCO.NS",
    "RECLTD.NS",
    "PFC.NS",
    "NTPC.NS",
    "NMDC.NS",
    "IOC.NS",
    "BPCL.NS",
    "HPCL.NS",
    "SAIL.NS",
    "TATASTEEL.NS",
    "GAIL.NS",
    "VEDL.NS",
    "HINDALCO.NS",
    "CANBK.NS",
    "PNB.NS",
    "BANKBARODA.NS",
    "UNIONBANK.NS",
    "OIL.NS",
    "PETRONET.NS",
    "NATIONALUM.NS",
    "MOIL.NS",
    "CASTROLIND.NS",
    "BHARATSE.NS",
    "GSFC.NS",
    "GNFC.NS",
]


def load_universe_symbols(include_all: bool = True) -> list[str]:
    """Load all unique value candidates from existing DB and core value universe."""
    symbols = list(DEEP_VALUE_UNIVERSE)

    if include_all and os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            db_syms = [r[0] for r in conn.execute("SELECT symbol FROM multibaggers").fetchall()]
            conn.close()
            for s in db_syms:
                if s and s not in symbols:
                    symbols.append(s)
        except Exception as e:
            print(f"Warning: Could not read symbols from DB: {e}")

    # Remove duplicates preserving order
    seen = set()
    unique_symbols = []
    for s in symbols:
        sym_clean = s.strip().upper()
        if sym_clean and sym_clean not in seen:
            seen.add(sym_clean)
            unique_symbols.append(sym_clean)

    return unique_symbols


def process_single_stock(symbol: str, dm: DataManager, market_regime: str) -> dict | None:
    """Fetch fundamentals & price, then compute institutional score and trade setup."""
    try:
        data = screener.get_stock_data_sync(symbol, dm=dm, include_quarterly=False)
        if not data or not isinstance(data, dict):
            return None

        # Calculate institutional score
        score_data = screener.calculate_institutional_score(data, market_regime=market_regime)
        score = float(score_data.get("total_score", 0.0))
        data["Score"] = round(score, 2)
        data["factor_penalties"] = score_data.get("factor_penalties", [])

        # Assign rating
        if score >= 80:
            data["Rating"] = "Strong Buy (Elite)"
        elif score >= 65:
            data["Rating"] = "Buy"
        elif score >= 50:
            data["Rating"] = "Hold"
        else:
            data["Rating"] = "Avoid"

        # Trade setup risk parameters
        screener.calculate_trade_setup(data)

        # Ensure Graham Number & Value Gap are strictly float
        if data.get("Graham_Number") is not None:
            try:
                data["Graham_Number"] = round(float(data["Graham_Number"]), 2)
            except (ValueError, TypeError):
                data["Graham_Number"] = None

        if data.get("Value_Gap%") is not None:
            try:
                data["Value_Gap%"] = round(float(data["Value_Gap%"]), 2)
            except (ValueError, TypeError):
                data["Value_Gap%"] = None

        return data
    except Exception as exc:
        print(f"[-] Error analyzing {symbol}: {exc}")
        return None


def scan_all_values(symbols: list[str] | None = None, max_workers: int = 5) -> int:
    """Main execution engine for scanning all value stocks."""
    print("=" * 75)
    print("🚀 SOVEREIGN TERMINAL — DEEP VALUE & VALUATION METRICS RESCAN")
    print("=" * 75)

    scan_list = symbols if symbols else load_universe_symbols(include_all=True)
    print(f"Target Universe: {len(scan_list)} stocks to scan.")

    # 1. Pre-load official NSE Bhavcopy into memory for fast price enrichment
    print("Pre-loading official NSE Bhavcopy data...")
    dm = DataManager()
    try:
        dm.bhavcopy_prices = download_bhavcopy()
        print(f"Loaded {len(dm.bhavcopy_prices)} quotes from official NSE Bhavcopy.")
    except Exception as e:
        print(f"Warning: Bhavcopy pre-load error (falling back to live feeds): {e}")

    # 2. Market Regime Analysis
    market_regime = screener.analyze_market_regime()
    print(f"Market Regime: {market_regime}")
    print(f"Starting concurrent scan with {max_workers} worker threads...\n")

    results = []
    completed = 0
    total = len(scan_list)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_sym = {
            executor.submit(process_single_stock, sym, dm, market_regime): sym
            for sym in scan_list
        }

        for future in as_completed(future_to_sym):
            completed += 1
            sym = future_to_sym[future]
            try:
                stock_data = future.result()
                if stock_data:
                    results.append(stock_data)
                    p = stock_data.get("Price", stock_data.get("current_price", 0.0))
                    vg = stock_data.get("Value_Gap%", "N/A")
                    print(f"[{completed:3d}/{total:3d}] {sym:<16} Price: ₹{p:<8.2f} Value Gap: {vg}%")
                else:
                    print(f"[{completed:3d}/{total:3d}] {sym:<16} (skipped/failed)")
            except Exception as e:
                print(f"[{completed:3d}/{total:3d}] {sym:<16} error: {e}")

    if not results:
        print("\n❌ No stocks successfully scanned.")
        return 0

    df_final = pd.DataFrame(results)

    # 3. Save to SQLite database
    print(f"\nPersisting {len(df_final)} scanned value stocks to SQLite ({DB_PATH})...")
    try:
        database.save_multibaggers(df_final, replace_existing=False)
        print("✅ Saved to 'multibaggers' table successfully.")
    except Exception as e:
        print(f"❌ Error saving to database: {e}")

    # 4. Save to CSVs
    report_csv = PROJECT_ROOT / "value_picks_report.csv"
    screener_csv = PROJECT_ROOT / "screener_results.csv"
    try:
        df_final.to_csv(report_csv, index=False)
        df_final.to_csv(screener_csv, index=False)
        print(f"✅ Saved reports to {report_csv.name} and {screener_csv.name}")
    except Exception as e:
        print(f"Warning: Could not save CSVs: {e}")

    # 5. Display Leaderboard
    print("\n" + "=" * 80)
    print("🏆 TOP DEEP-VALUE PICKS LEADERBOARD (By Value Gap & Score)")
    print("=" * 80)

    display_cols = ["Symbol", "Price", "PE_Ratio", "Graham_Number", "Value_Gap%", "Score", "Rating"]
    available_cols = [c for c in display_cols if c in df_final.columns]

    # Sort by Value_Gap% descending (filtering out NaN)
    if "Value_Gap%" in df_final.columns:
        df_sorted = df_final.dropna(subset=["Value_Gap%"]).sort_values(
            by=["Value_Gap%", "Score"], ascending=[False, False]
        )
    else:
        df_sorted = df_final.sort_values(by="Score", ascending=False)

    print(df_sorted[available_cols].head(20).to_string(index=False))
    print("=" * 80)
    print(f"\n🎉 Value Rescan Complete: {len(results)}/{total} stocks updated.")
    return len(results)


def main():
    parser = argparse.ArgumentParser(description="Rescan all value stocks and valuation metrics")
    parser.add_argument(
        "--all",
        action="store_true",
        default=True,
        help="Scan all tracked stocks in DB plus deep value universe",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default=None,
        help="Comma-separated symbols to scan (e.g. COALINDIA.NS,ONGC.NS)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=5,
        help="Concurrent worker threads (default: 5)",
    )
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")] if args.symbols else None
    scan_all_values(symbols=symbols, max_workers=args.workers)


if __name__ == "__main__":
    main()
