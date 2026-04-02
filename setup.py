# setup.py
"""
Sovereign AI Trading Engine — Automated Setup (v4.0)
Handles environment initialization, database creation, and initial data warm-up.
"""
import os
import sys
import shutil
import subprocess
from datetime import datetime

# Ensure project root is in path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def print_step(step, text):
    print(f"\n[{step}] {text}")
    print("-" * 60)

def setup_environment():
    print_step(1, "Environment Initialization")
    if not os.path.exists(".env"):
        if os.path.exists(".env.example"):
            shutil.copy(".env.example", ".env")
            print("✅ Created .env from .env.example")
        else:
            with open(".env", "w") as f:
                f.write("# Sovereign AI Environment\n")
                f.write("TELEGRAM_BOT_TOKEN=\n")
                f.write("TELEGRAM_CHAT_ID=\n")
                f.write("DATABASE_URL=sqlite:///stocks.db\n")
            print("✅ Created blank .env file")
    else:
        print("ℹ️  .env file already exists. Skipping.")

def setup_database():
    print_step(2, "Database Initialization")
    try:
        from db.repository import init_db
        init_db()
        print("✅ Database schemas initialized.")
    except Exception as e:
        print(f"❌ Database initialization failed: {e}")
        sys.exit(1)

def warmup_data():
    print_step(3, "Data Warm-up (Benchmark)")
    try:
        import yfinance as yf
        print("Fetching Nifty 50 (^NSEI) for benchmark calibration...")
        nifty = yf.Ticker("^NSEI")
        hist = nifty.history(period="2y")
        if not hist.empty:
            print(f"✅ Fetched {len(hist)} days of benchmark data.")
        else:
            print("⚠️  No benchmark data found. Check your internet connection.")
    except Exception as e:
        print(f"⚠️  Benchmark warm-up failed: {e}")

def initialize_ml():
    print_step(4, "ML Model Initialization")
    if os.path.exists("xgboost_meta_model.pkl"):
        print("ℹ️  XGBoost model already exists. Skipping training.")
        return

    try:
        from modules.hybrid_scoring import train_hybrid_model
        print("Attempting cold-start training...")
        success = train_hybrid_model()
        if success:
            print("✅ ML Model trained successfully.")
        else:
            print("ℹ️  Cold-start training skipped (insufficient PIT data).")
            print("   Run a full scan first to populate the database.")
    except ImportError:
        print("⚠️  ML modules (xgboost/shap) not found. Skipping ML init.")
    except Exception as e:
        print(f"⚠️  ML initialization failed: {e}")

def run_health_check():
    print_step(5, "Final Health Check")
    try:
        # Import sovereign-cli cmd_health if possible, or just print summary
        print("System Summary:")
        print(f"  Project Root: {PROJECT_ROOT}")
        print(f"  Python:       {sys.version.split()[0]}")
        print(f"  Timestamp:    {datetime.now().isoformat()}")
        
        dbs = ["stocks.db", "pit_store.db", "data_cache.db"]
        for db in dbs:
            status = "PRESENT" if os.path.exists(db) else "MISSING"
            print(f"  Database {db:15}: {status}")
            
        print("\n✨ Setup Complete! Run 'python sovereign-cli.py health' for deep audit.")
    except Exception as e:
        print(f"⚠️  Health check encountered issues: {e}")

if __name__ == "__main__":
    print("============================================================")
    print("   Sovereign AI Trading Engine - Setup Wizard (v4.0)")
    print("============================================================")
    
    setup_environment()
    setup_database()
    warmup_data()
    initialize_ml()
    run_health_check()
