#!/usr/bin/env python3
"""
Sovereign AI Trading Engine - Unified CLI (v4.0)
The authoritative entry point for all engine operations, research, and maintenance.
"""

import sys
import io
import argparse
import os
import asyncio
import json
import pandas as pd
from datetime import datetime

# Ensure project modules are importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from db.repository import get_connection

# Global Paths for v9.6 Automation
SIGNALS_LOG = "paper_trade_signals.json"

def print_header(text):
    print(f"\n{'='*60}")
    print(f" {text}")
    print(f"{'='*60}")

# ══════════════════════════════════════════════════════════════════════════════
# COMMAND: DB Group
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_db_init(args):
    """Initialize database schemas."""
    print_header("Database Initialization")
    from db.repository import init_db
    init_db()
    print("✅ Database schemas initialized.")

async def cmd_db_stats(args):
    """Summarize database table counts and health."""
    print_header("Database Statistics")
    dbs = ["stocks.db", "pit_store.db", "data_cache.db"]
    for db_name in dbs:
        if not os.path.exists(db_name):
            print(f"⚠️  {db_name}: MISSING")
            continue
        try:
            conn = get_connection() # Uses stocks.db by default usually
            # Note: repository.get_connection is tuned for stocks.db. 
            # For others we might need raw sqlite3.
            import sqlite3
            conn_raw = sqlite3.connect(db_name)
            cursor = conn_raw.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [t[0] for t in cursor.fetchall()]
            print(f"\n📂 {db_name}:")
            for t in tables:
                cursor.execute(f"SELECT count(*) FROM {t}")
                count = cursor.fetchone()[0]
                print(f"  {t:20}: {count} rows")
            conn_raw.close()
        except Exception as e:
            print(f"  ❌ Error reading {db_name}: {e}")

async def cmd_db_cleanup(args):
    """Run database vacuum and maintenance."""
    print_header("Database Cleanup & Maintenance")
    from scripts.internal.db_cleanup import run_cleanup
    run_cleanup()

async def cmd_db_dups(args):
    """Identify and optionally clean duplicate entries in stocks.db."""
    print_header("Duplicate Record Forensic")
    import sqlite3
    try:
        conn = sqlite3.connect("stocks.db")
        cursor = conn.cursor()
        
        # Check multibaggers table
        cursor.execute("SELECT symbol, count(*) FROM multibaggers GROUP BY symbol HAVING count(*) > 1")
        dups = cursor.fetchall()
        
        if not dups:
            print("✅ No duplicate symbols found in 'multibaggers' table.")
        else:
            print(f"⚠️  Found {len(dups)} duplicate symbols in 'multibaggers':")
            for symbol, count in dups:
                print(f"  - {symbol:15}: {count} occurrences")
        
        # Check other related tables if they exist
        for table in ['valuation_metrics', 'fundamentals_pit']:
            try:
                cursor.execute(f"SELECT symbol, count(*) FROM {table} GROUP BY symbol HAVING count(*) > 1")
                t_dups = cursor.fetchall()
                if t_dups:
                    print(f"\n📂 Duplicate symbols in '{table}': {len(t_dups)}")
            except sqlite3.OperationalError:
                pass
                
        conn.close()
    except Exception as e:
        print(f"❌ Error during duplicate check: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# COMMAND: SCAN Group
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_scan_run(args):
    """Run a specific universe scan."""
    print_header(f"Scan Execution: {args.type.upper()}")
    
    script_map = {
        "commodities": "scan_commodities.py",
        "master": "scan_master_picks.py",
        "requested": "scan_requested_symbols.py",
        "swarm": "scan_swarm.py",
        "value": "scan_value_picks.py",
        "user": "scan_user_picks_v5.py",
        "missing": "scan_missing.py",
        "tmpv": "scan_tmpv.py",
        "quick": "screener.py"
    }
    
    script_name = script_map.get(args.type.lower())
    if not script_name:
        print(f"❌ Unknown scan type: {args.type}")
        return

    import subprocess
    cmd = [sys.executable]
    if args.type == "quick":
        cmd.append("screener.py")
        if args.smoke: cmd.append("--smoke")
    else:
        cmd.append(os.path.join("scripts", "internal", script_name))
        if args.tickers:
            cmd.extend(["--tickers", args.tickers])
        if args.deep:
            cmd.append("--deep")
        if args.push:
            cmd.append("--push")

    print(f"🚀 Running: {' '.join(cmd)}")
    subprocess.run(cmd)

# ══════════════════════════════════════════════════════════════════════════════
# COMMAND: ML Group
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_ml_train(args):
    """Train the XGBoost Meta-Model."""
    print_header("ML Operations: Training")
    from modules.hybrid_scoring import train_hybrid_model
    train_hybrid_model()

async def cmd_ml_explain(args):
    """Explain a specific stock's score via SHAP."""
    print_header(f"ML Operations: Explainability ({args.symbol})")
    from scripts.internal.diagnose_scores import explain_stock
    # Assuming analyze_stock.py or similar
    import subprocess
    subprocess.run([sys.executable, "scripts/internal/analyze_stock.py", "--symbol", args.symbol])

# ══════════════════════════════════════════════════════════════════════════════
# COMMAND: SYSTEM Group
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_health(args):
    """System-wide health check."""
    """Run v9.6 health check diagnostic via isolated subprocess."""
    print_header("Sovereign Health Audit")
    import subprocess
    import sys
    try:
        script_path = os.path.join("scripts", "internal", "diagnose.py")
        subprocess.run([sys.executable, script_path], check=True)
    except subprocess.CalledProcessError:
        print("❌ Health check failed.")
    except Exception as e:
        print(f"❌ Error invoking health check: {e}")

async def cmd_regime(args):
    """Check and display the current market regime."""
    print_header("Sovereign Regime Audit")
    from modules.market_data import MarketDataProvider
    try:
        provider = MarketDataProvider()
        res = provider.get_market_regime()
        print(f"Current Regime: {res.get('regime', 'UNKNOWN')}")
        if 'details' in res and 'momentum_accel' in res['details']:
            print(f"Acceleration: {res['details']['momentum_accel']:.2f}")
    except Exception as e:
        print(f"❌ Error checking regime: {e}")

async def cmd_paper_trade(args):
    """Run live signal logging and paper trading logic."""
    print_header("Sovereign Paper Trade: Live Signal Generation")
    
    # 1. Rebalance Logic (Quarterly Checks: Feb, May, Aug, Nov)
    today = datetime.now()
    rebalance_months = [2, 5, 8, 11]
    is_rebalance_date = today.month in rebalance_months and today.day == 1
    
    if not is_rebalance_date and not args.force:
        print(f"⚠️ Today is not a rebalance date ({today.date()}). No signals will be generated.")
        print("Use --force to override and generate a signal manually.")
        return

    # 2. Market Regime Check
    from modules.market_data import MarketDataProvider
    provider = MarketDataProvider()
    regime_res = provider.get_market_regime()
    regime = regime_res['regime']
    
    # 3. Universe Preparation (Top 50 by default)
    from ticker_list import TICKERS
    universe = TICKERS[:args.universe]
    print(f"📡 Scanning Universe of {len(universe)} stocks...")

    # 4. Fetch Fundamentals and Score
    # Wrapping synchronous yfinance scan in a thread to keep the event loop responsive (v9.6)
    results = await asyncio.to_thread(_run_paper_trade_scan, universe, regime)
    
    if not results:
        print("❌ Failed to fetch data for scan (Empty results or error during scan).")
        return

    df_snapshot = pd.DataFrame(results)
    
    # 5. Concentration Cap: 2-Quarter Consecutive Hold Constraint
    log_file = SIGNALS_LOG
    history = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            try:
                history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []

    prev1_picks = history[-1].get('picks', []) if len(history) >= 1 else []
    prev2_picks = history[-2].get('picks', []) if len(history) >= 2 else []
    blocked_symbols = set(prev1_picks) & set(prev2_picks)
    
    if blocked_symbols:
        print(f"🚫 Blocked Symbols (Hold Limit): {', '.join(blocked_symbols)}")
        df_snapshot = df_snapshot[~df_snapshot['Symbol'].isin(blocked_symbols)]

    # 6. Final Select and Log
    # Hard filter for zero-score data failures (v9.6)
    df_snapshot = df_snapshot[df_snapshot['total_score'] > 5]
    top_picks = df_snapshot.nlargest(10, 'total_score')
    picks = top_picks['Symbol'].tolist()
    
    exposure_map = {"BULL": 1.0, "SIDEWAYS": 0.5, "BEAR": 0.1, "VOLATILE": 0.3}
    exposure = exposure_map.get(regime, 0.5)

    signal_entry = {
        "timestamp": today.isoformat(),
        "date": str(today.date()),
        "regime": regime,
        "exposure": exposure,
        "picks": picks,
        "metrics": top_picks[['Symbol', 'total_score', 'Price']].to_dict('records')
    }

    history.append(signal_entry)
    with open(SIGNALS_LOG, "w") as f:
        json.dump(history, f, indent=4)

    print(f"\n✅ REBALANCE SIGNAL GENERATED: {regime} (Exposure: {exposure:.0%})")
    print(f"Top Picks: {', '.join(picks[:3])}...")
    print(f"Log updated: {SIGNALS_LOG}")

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _run_paper_trade_scan(universe, regime):
    """Synchronous core loop for paper-trade scanning. Called via asyncio.to_thread."""
    import yfinance as yf
    from modules.scoring import calculate_institutional_score
    from modules.fundamentals import calculate_piotroski_f_score
    
    results = []
    for symbol in universe:
        try:
            print(f"  Fetching: {symbol}", end="\r")
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Simplified for speed in live scan, mirroring backtest logic
            data = {
                "Symbol": symbol,
                "Price": info.get("currentPrice", 0),
                "Sector": info.get("sector", "Unknown"),
                "ROE%": info.get("returnOnEquity", 0) * 100,
                "Sales_Growth_TTM%": info.get("revenueGrowth", 0) * 100,
                "Debt_Equity": info.get("debtToEquity", 0) / 100 if info.get("debtToEquity") else 0,
                "F_Score": calculate_piotroski_f_score(ticker),
                "PE_Ratio": info.get("trailingPE", 0),
                "Market_Cap": info.get("marketCap", 0),
                "Down_From_52W_High%": ((info.get("fiftyTwoWeekHigh", 1) - info.get("currentPrice", 1)) / info.get("fiftyTwoWeekHigh", 1)) * 100
            }
            
            score_res = calculate_institutional_score(data, market_regime=regime)
            data['total_score'] = score_res['total_score']
            results.append(data)
        except Exception:
            continue
    return results

# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

async def main():
    parser = argparse.ArgumentParser(description="Sovereign AI Trading Engine - Unified CLI (v4.0)")
    subparsers = parser.add_subparsers(dest="group", help="Command groups")

    # DB Group
    db_parser = subparsers.add_parser("db", help="Database management")
    db_sub = db_parser.add_subparsers(dest="command")
    db_sub.add_parser("init", help="Initialize schema")
    db_sub.add_parser("stats", help="Show table counts")
    db_sub.add_parser("cleanup", help="Vacuum and optimize")

    # SCAN Group
    scan_parser = subparsers.add_parser("scan", help="Run universe scans")
    scan_parser.add_argument("type", choices=["quick", "commodities", "master", "requested", "swarm", "value", "user", "missing", "tmpv"])
    scan_parser.add_argument("--smoke", action="store_true", help="Quick scan dry-run")
    scan_parser.add_argument("--tickers", help="Comma-separated tickers for swarm/requested")
    scan_parser.add_argument("--deep", action="store_true", help="Run high-fidelity deep simulation")
    scan_parser.add_argument("--push", action="store_true", help="Push conviction updates to database")

    # ML Group
    ml_parser = subparsers.add_parser("ml", help="Machine Learning operations")
    ml_sub = ml_parser.add_subparsers(dest="command")
    ml_sub.add_parser("train", help="Train meta-model")
    ml_explain = ml_sub.add_parser("explain", help="SHAP explainability")
    ml_explain.add_argument("--symbol", required=True)

    # RESEARCH Group
    res_parser = subparsers.add_parser("research", help="Deep research tools")
    res_sub = res_parser.add_subparsers(dest="command")
    res_sub.add_parser("alpha", help="Calculate alpha attribution")
    res_sub.add_parser("vif", help="Multi-collinearity check")
    res_sub.add_parser("liquidity", help="Run liquidity simulator")

    # BACKTEST Group
    bt_parser = subparsers.add_parser("backtest", help="Strategy walk-forward backtesting")
    bt_sub = bt_parser.add_subparsers(dest="command")
    
    qarp_parser = bt_sub.add_parser("qarp", help="QARP 8-Factor Walk-Forward")
    qarp_parser.add_argument("--years", type=int, default=2, help="Years of lookback (max 3)")
    qarp_parser.add_argument("--rebalance", choices=["monthly", "quarterly"], default="quarterly")
    qarp_parser.add_argument("--universe", choices=["top-50", "top-100", "nifty-500"], default="top-50")
    
    sma_parser = bt_sub.add_parser("sma", help="Technical SMA Crossover (VectorBT)")
    sma_parser.add_argument("--symbol", default="RELIANCE.NS")
    sma_parser.add_argument("--fast", type=int, default=20)
    sma_parser.add_argument("--slow", type=int, default=50)

    # SYSTEM Group
    sys_parser = subparsers.add_parser("sys", help="System operations")
    sys_sub = sys_parser.add_subparsers(dest="command")
    sys_sub.add_parser("health", help="Run health check")
    sys_sub.add_parser("setup", help="Run first-time setup")
    sys_sub.add_parser("regime", help="Check market regime")
    sys_sub.add_parser("dups", help="Find duplicate symbols in DB")

    # PAPER-TRADE Group (v9.1 Bridge)
    pt_parser = subparsers.add_parser("paper-trade", help="Live signal logging and paper trading")
    pt_parser.add_argument("--universe", type=int, default=50, help="Number of top tickers to scan")
    pt_parser.add_argument("--force", action="store_true", help="Log even if not a standard rebalance date")

    args = parser.parse_args()

    if args.group == "db":
        if args.command == "init": await cmd_db_init(args)
        elif args.command == "stats": await cmd_db_stats(args)
        elif args.command == "cleanup": await cmd_db_cleanup(args)
    elif args.group == "scan":
        await cmd_scan_run(args)
    elif args.group == "ml":
        if args.command == "train": await cmd_ml_train(args)
        elif args.command == "explain": await cmd_ml_explain(args)
    elif args.group == "backtest":
        if args.command == "qarp":
            # This will call our new script
            import subprocess
            cmd = [sys.executable, "backtest_qarp.py", "--years", str(args.years), "--rebalance", args.rebalance, "--universe", args.universe]
            subprocess.run(cmd)
        elif args.command == "sma":
            import subprocess
            cmd = [sys.executable, "backtest_engine.py", "--symbol", args.symbol, "--fast", str(args.fast), "--slow", str(args.slow)]
            subprocess.run(cmd)
    elif args.group == "sys":
        if args.command == "health": await cmd_health(args)
        elif args.command == "regime": await cmd_regime(args)
        elif args.command == "dups": await cmd_db_dups(args)
        elif args.command == "setup": 
            import setup
            setup.setup_environment()
            setup.setup_database()
    elif args.group == "paper-trade":
        await cmd_paper_trade(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    # Ensure UTF-8 output on Windows at runtime only (isolated from tests)
    import io
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    asyncio.run(main())
