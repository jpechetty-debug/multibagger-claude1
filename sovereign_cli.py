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
import sqlite3 as _sqlite3
import pandas as pd
from types import SimpleNamespace
from datetime import datetime

# Ensure project modules are importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from db.repository import get_connection
from modules.data_service import MarketDataProvider

# Use a local proxy so tests can patch ``sovereign_cli.sqlite3.connect``
# without mutating the global stdlib sqlite module.
sqlite3 = SimpleNamespace(
    connect=_sqlite3.connect,
    OperationalError=_sqlite3.OperationalError,
)

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

async def cmd_db_verify(args):
    """Verify database integrity."""
    print_header("Database Verification")
    import subprocess
    subprocess.run([sys.executable, os.path.join("scripts", "internal", "verify_db.py")])

async def cmd_db_stats(args):
    """Summarize database table counts and health."""
    print_header("Database Statistics")
    dbs = ["stocks.db", "pit_store.db", "data_cache.db"]
    for db_name in dbs:
        db_path = os.path.join("runtime", db_name)
        if not os.path.exists(db_path):
            print(f"⚠️  {db_path}: MISSING")
            continue
        try:
            import sqlite3
            conn_raw = sqlite3.connect(db_path)
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
    # We moved db_cleanup.py to scripts/internal/ in a previous step probably, 
    # but let's check if it exists there or we should use wipe_junk_data.py
    import subprocess
    script = "wipe_junk_data.py" if args.wipe else "check_db.py"
    subprocess.run([sys.executable, os.path.join("scripts", "internal", script)])

async def cmd_db_dups(args):
    """Identify and optionally clean duplicate entries in stocks.db."""
    print_header("Duplicate Record Forensic")
    try:
        db_path = os.path.join("runtime", "stocks.db")
        conn = sqlite3.connect(db_path)
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
        "quick": "screener.py",
        "microcap": "microcap_screener.py"
    }
    
    script_name = script_map.get(args.type.lower())
    if not script_name:
        print(f"❌ Unknown scan type: {args.type}")
        return

    import subprocess
    cmd = [sys.executable, os.path.join("scripts", "internal", script_name)]
    
    if args.type in ["quick", "microcap"]:
        if args.smoke: cmd.append("--smoke")
    else:
        if args.tickers:
            cmd.extend(["--tickers", args.tickers])
        if args.deep:
            cmd.append("--deep")
        if args.push:
            cmd.append("--push")

    print(f"🚀 Running: {' '.join(cmd)}")
    subprocess.run(cmd)

async def cmd_rs_ingest(args):
    """Ingest RS CSV signals into the multibaggers table."""
    print_header("RS Signals: Ingest")
    # All are in scripts/internal now
    import subprocess
    subprocess.run([sys.executable, os.path.join("scripts", "internal", "ingest_rs_signals.py"), "--csv-path", args.csv_path])


async def cmd_rs_enrich(args):
    """Enrich RS rows that have not been audited yet."""
    print_header("RS Signals: Enrich")
    import subprocess
    subprocess.run([
        sys.executable, 
        os.path.join("scripts", "internal", "enrich_rs_signals.py"),
        "--db-path", args.db_path,
        "--delay-seconds", str(args.delay_seconds),
        "--market-regime", args.market_regime
    ])


async def cmd_rs_cleanup(args):
    """Delete RS rows for the requested symbols."""
    print_header("RS Signals: Cleanup")
    import subprocess
    cmd = [sys.executable, os.path.join("scripts", "internal", "cleanup_signals.py"), "--db-path", args.db_path]
    cmd.extend(["--symbols"] + args.symbols)
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
    import subprocess
    subprocess.run([sys.executable, os.path.join("scripts", "internal", "diagnose_scores.py"), "--symbol", args.symbol])

# ══════════════════════════════════════════════════════════════════════════════
# COMMAND: SYSTEM Group
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_health(args):
    """System-wide health check."""
    print_header("Sovereign Health Audit")
    import subprocess
    try:
        script_path = os.path.join("scripts", "internal", "diagnose.py")
        subprocess.run([sys.executable, script_path], check=True)
    except Exception as e:
        print(f"❌ Health check failed: {e}")

async def cmd_regime(args):
    """Check and display the current market regime."""
    print_header("Sovereign Regime Audit")
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
    
    # Rebalance months check
    today = datetime.now()
    rebalance_months = [2, 5, 8, 11]
    is_rebalance_date = today.month in rebalance_months and today.day == 1
    
    if not is_rebalance_date and not args.force:
        print(f"⚠️ Today is not a rebalance date ({today.date()}). No signals will be generated.")
        print("Use --force to override.")
        return

    provider = MarketDataProvider()
    regime_res = provider.get_market_regime()
    regime = regime_res['regime']
    
    from ticker_list import TICKERS
    universe = TICKERS[:args.universe]
    print(f"📡 Scanning Universe of {len(universe)} stocks...")

    results = await asyncio.to_thread(_run_paper_trade_scan, universe, regime)
    if not results:
        print("❌ Scan failed.")
        return

    df_snapshot = pd.DataFrame(results)
    
    # Simple history check
    log_file = SIGNALS_LOG
    history = []
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            try: history = json.load(f)
            except: history = []

    # Final Select
    df_snapshot = df_snapshot[df_snapshot['total_score'] > 5]
    if history:
        recent_picks = [entry.get("picks", []) for entry in history[-2:]]
        held_counts = {}
        for pick_list in recent_picks:
            for pick in pick_list:
                held_counts[pick] = held_counts.get(pick, 0) + 1
        concentration_block = {symbol for symbol, count in held_counts.items() if count >= 2}
        if concentration_block:
            df_snapshot = df_snapshot[~df_snapshot["Symbol"].isin(concentration_block)]
    top_picks = df_snapshot.nlargest(10, 'total_score')
    picks = top_picks['Symbol'].tolist()
    
    signal_entry = {
        "timestamp": today.isoformat(),
        "date": str(today.date()),
        "regime": regime,
        "picks": picks,
        "metrics": top_picks[['Symbol', 'total_score', 'Price']].to_dict('records')
    }

    history.append(signal_entry)
    with open(SIGNALS_LOG, "w") as f:
        json.dump(history, f, indent=4)

    print(f"\n✅ REBALANCE SIGNAL GENERATED: {regime}")
    print(f"Top Picks: {', '.join(picks[:3])}...")

def _run_paper_trade_scan(universe, regime):
    import yfinance as yf
    from modules.scoring import calculate_institutional_score
    from modules.fundamentals import calculate_piotroski_f_score
    
    results = []
    for symbol in universe:
        try:
            print(f"  Fetching: {symbol}", end="\r")
            ticker = yf.Ticker(symbol)
            info = ticker.info
            data = {
                "Symbol": symbol,
                "Price": info.get("currentPrice", 0),
                "Sector": info.get("sector", "Unknown"),
                "ROE%": info.get("returnOnEquity", 0) * 100,
                "Sales_Growth_TTM%": info.get("revenueGrowth", 0) * 100,
                "F_Score": calculate_piotroski_f_score(ticker),
                "PE_Ratio": info.get("trailingPE", 0),
                "Market_Cap": info.get("marketCap", 0),
                "Down_From_52W_High%": ((info.get("fiftyTwoWeekHigh", 1) - info.get("currentPrice", 1)) / info.get("fiftyTwoWeekHigh", 1)) * 100
            }
            score_res = calculate_institutional_score(data, market_regime=regime)
            data['total_score'] = score_res['total_score']
            results.append(data)
        except: continue
    return results

async def main():
    parser = argparse.ArgumentParser(description="Sovereign AI Trading Engine - Unified CLI (v4.0)")
    subparsers = parser.add_subparsers(dest="group", help="Command groups")

    # DB Group
    db_parser = subparsers.add_parser("db", help="Database management")
    db_sub = db_parser.add_subparsers(dest="command")
    db_sub.add_parser("init", help="Initialize schema")
    db_sub.add_parser("stats", help="Show table counts")
    db_sub.add_parser("verify", help="Run database integrity check")
    db_cleanup = db_sub.add_parser("cleanup", help="Run maintenance/cleanup")
    db_cleanup.add_argument("--wipe", action="store_true", help="Wipe junk data")

    # SCAN Group
    scan_parser = subparsers.add_parser("scan", help="Run universe scans")
    scan_parser.add_argument("type", choices=["quick", "microcap", "commodities", "master", "requested", "swarm", "value", "user", "missing", "tmpv"])
    scan_parser.add_argument("--smoke", action="store_true", help="Quick scan dry-run")
    scan_parser.add_argument("--tickers", help="Comma-separated tickers for swarm/requested")
    scan_parser.add_argument("--deep", action="store_true", help="Run high-fidelity deep simulation")
    scan_parser.add_argument("--push", action="store_true", help="Push conviction updates to database")

    # RS Group
    rs_parser = subparsers.add_parser("rs", help="Relative strength signal operations")
    rs_sub = rs_parser.add_subparsers(dest="command")
    rs_ingest = rs_sub.add_parser("ingest", help="Ingest RS CSV export")
    rs_ingest.add_argument("--csv-path", default="tmp_rs_data.csv")
    rs_enrich = rs_sub.add_parser("enrich", help="Enrich RS rows")
    rs_enrich.add_argument("--db-path", default="runtime/stocks.db")
    rs_enrich.add_argument("--delay-seconds", type=float, default=2.0)
    rs_enrich.add_argument("--market-regime", default="SIDEWAYS")
    rs_cleanup = rs_sub.add_parser("cleanup", help="Delete RS rows")
    rs_cleanup.add_argument("--symbols", nargs="+", required=True)
    rs_cleanup.add_argument("--db-path", default="runtime/stocks.db")

    # ML Group
    ml_parser = subparsers.add_parser("ml", help="Machine Learning operations")
    ml_sub = ml_parser.add_subparsers(dest="command")
    ml_sub.add_parser("train", help="Train meta-model")
    ml_explain = ml_sub.add_parser("explain", help="SHAP explainability")
    ml_explain.add_argument("--symbol", required=True)

    # BACKTEST Group
    bt_parser = subparsers.add_parser("backtest", help="Strategy walk-forward backtesting")
    bt_sub = bt_parser.add_subparsers(dest="command")
    qarp_parser = bt_sub.add_parser("qarp", help="QARP 8-Factor")
    qarp_parser.add_argument("--years", type=int, default=2)
    qarp_parser.add_argument("--rebalance", choices=["monthly", "quarterly"], default="quarterly")
    qarp_parser.add_argument("--universe", choices=["top-50", "top-100", "nifty-500"], default="top-50")
    engine_parser = bt_sub.add_parser("engine", help="Main backtest engine (VectorBT)")
    engine_parser.add_argument("--symbol", default="RELIANCE.NS")

    # SYSTEM Group
    sys_parser = subparsers.add_parser("sys", help="System operations")
    sys_sub = sys_parser.add_subparsers(dest="command")
    sys_sub.add_parser("health", help="Run health check")
    sys_sub.add_parser("setup", help="Run first-time setup")
    sys_sub.add_parser("regime", help="Check market regime")
    sys_sub.add_parser("dups", help="Find duplicate symbols in DB")

    # PAPER-TRADE Group
    pt_parser = subparsers.add_parser("paper-trade", help="Live signal logging")
    pt_parser.add_argument("--universe", type=int, default=50)
    pt_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()

    if args.group == "db":
        if args.command == "init": await cmd_db_init(args)
        elif args.command == "stats": await cmd_db_stats(args)
        elif args.command == "verify": await cmd_db_verify(args)
        elif args.command == "cleanup": await cmd_db_cleanup(args)
    elif args.group == "scan":
        await cmd_scan_run(args)
    elif args.group == "rs":
        if args.command == "ingest": await cmd_rs_ingest(args)
        elif args.command == "enrich": await cmd_rs_enrich(args)
        elif args.command == "cleanup": await cmd_rs_cleanup(args)
    elif args.group == "ml":
        if args.command == "train": await cmd_ml_train(args)
        elif args.command == "explain": await cmd_ml_explain(args)
    elif args.group == "backtest":
        import subprocess
        if args.command == "qarp":
            cmd = [sys.executable, "scripts/internal/backtest_qarp.py", "--years", str(args.years), "--rebalance", args.rebalance, "--universe", args.universe]
            subprocess.run(cmd)
        elif args.command == "engine":
            cmd = [sys.executable, "scripts/internal/backtest_engine.py", "--symbol", args.symbol]
            subprocess.run(cmd)
    elif args.group == "sys":
        if args.command == "health": await cmd_health(args)
        elif args.command == "regime": await cmd_regime(args)
        elif args.command == "dups": await cmd_db_dups(args)
        elif args.command == "setup":
            import subprocess
            subprocess.run([sys.executable, "scripts/internal/setup.py"])
    elif args.group == "paper-trade":
        await cmd_paper_trade(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    asyncio.run(main())
