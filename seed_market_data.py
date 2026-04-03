"""
Sovereign Market Data Seeder (v1.0)
Uses internal repository logic to ensure schema compatibility (63 columns).
"""
import sys, os
import pandas as pd
import asyncio
from datetime import datetime

# Add root project and Newmultibagger-main to sys.path
root = os.getcwd()
sys.path.insert(0, root)

import db.repository as repository
import screener

# High-Conviction Indian Bluechips & Midcaps
TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "BHARTIARTL.NS", "BAJFINANCE.NS", "SBIN.NS", "LT.NS",
    "ITC.NS", "KOTAKBANK.NS", "AXISBANK.NS", "MARUTI.NS", "TITAN.NS",
    "ADANIENT.NS", "SUNPHARMA.NS", "ULTRACEMCO.NS", "ASIANPAINT.NS", "NESTLEIND.NS"
]

async def seed_data():
    print(f"🚀 Initializing Database via Repository Layer...")
    repository.init_db()
    
    print(f"🔍 Fetching Alpha Signals for {len(TICKERS)} tickers...")
    results = []
    
    # We use some dummy data/minimal fetch to ensure speed for this seed
    # But we map it to the expected columns in save_multibaggers
    for symbol in TICKERS:
        try:
            print(f"  Processing {symbol}...", end="\r")
            # Minimal data to satisfy core scoring logic or repo requirements
            # In a real scan, screener.get_stock_data(symbol) would be used
            # For seeding, we'll try to fetch live data if possible
            data = await screener.get_stock_data(symbol)
            
            if data and data.get('Symbol'):
                # Apply scoring
                regime = screener.analyze_market_regime()
                score_res = screener.calculate_institutional_score(data, market_regime=regime)
                data['Score'] = score_res['total_score']
                
                # Basic Rating
                if data['Score'] >= 80: data["Rating"] = "Strong Buy"
                elif data['Score'] >= 65: data["Rating"] = "Buy"
                else: data["Rating"] = "Hold"
                
                # Map to capital case for repo layer
                # The repo expects: Symbol, Price, Sector, Score, etc.
                # data already has symbol, price, etc.
                
                results.append(data)
                print(f"  ✅ {symbol}: Score {data['Score']:.1f}")
        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            
    if results:
        df = pd.DataFrame(results)
        print(f"\n💾 Saving {len(results)} records to multibaggers...")
        repository.save_multibaggers(df)
        print("✅ Seeding complete.")
    else:
        print("❌ No data fetched. Database remains empty.")

if __name__ == "__main__":
    asyncio.run(seed_data())
