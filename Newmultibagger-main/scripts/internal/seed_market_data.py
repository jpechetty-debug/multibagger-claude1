"""
Sovereign Market Data Seeder (v1.0)
Uses internal repository logic to ensure schema compatibility (63 columns).
"""

import asyncio
import os
import sys

import pandas as pd

# Add root project and Newmultibagger-main to sys.path
root = os.getcwd()
sys.path.insert(0, root)

import screener

import db.repository as repository

# High-Conviction Indian Bluechips & Midcaps
TICKERS = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "INFY.NS",
    "ICICIBANK.NS",
    "HINDUNILVR.NS",
    "BHARTIARTL.NS",
    "BAJFINANCE.NS",
    "SBIN.NS",
    "LT.NS",
    "ITC.NS",
    "KOTAKBANK.NS",
    "AXISBANK.NS",
    "MARUTI.NS",
    "TITAN.NS",
    "ADANIENT.NS",
    "SUNPHARMA.NS",
    "ULTRACEMCO.NS",
    "ASIANPAINT.NS",
    "NESTLEIND.NS",
]


async def process_ticker(symbol, semaphore):
    async with semaphore:
        try:
            print(f"  [SCAN] Processing {symbol}...")
            data = await screener.get_stock_data(symbol)

            # Critical Validation Gate (v12.0 Hardening)
            if not isinstance(data, dict):
                print(f"  ERR {symbol}: Invalid response type")
                return None

            if data.get("_fetch_error"):
                detail = data.get("_fetch_error_detail", "")
                print(f"  ERR {symbol}: {data.get('_fetch_error')} | {detail}")
                return None

            price = data.get("Price")
            if price is None or not screener._is_finite_number(price) or float(price) <= 0:
                print(f"  ERR {symbol}: Non-positive price detected ({price})")
                return None

            # Skip skeletal results (missing core fundamentals)
            if (
                not data.get("Market_Cap_Cr")
                or not data.get("Sector")
                or data.get("Sector") == "Unknown"
            ):
                print(f"  ERR {symbol}: Skeletal fundamentals, skipping")
                return None

            # Apply scoring & regime analysis
            regime = screener.analyze_market_regime()
            score_res = screener.calculate_institutional_score(data, market_regime=regime)
            data["Score"] = score_res["total_score"]

            # Institutional Conviction Mapping (v11.0 standards)
            if data["Score"] >= 92:
                data["Rating"] = "Strong Buy"
            elif data["Score"] >= 80:
                data["Rating"] = "Buy"
            elif data["Score"] >= 60:
                data["Rating"] = "Watch"
            else:
                data["Rating"] = "Hold"

            print(f"  OK {symbol}: Score {data['Score']:.1f} ({data['Rating']})")
            return data

        except Exception as e:
            print(f"  ERR {symbol}: Unexpected error: {e}")
            return None


async def seed_data():
    print("--- Initializing Database via Repository Layer ---")
    repository.init_db()

    print(f"--- Fetching Alpha Signals for {len(TICKERS)} tickers ---")

    semaphore = asyncio.Semaphore(5)
    tasks = [process_ticker(symbol, semaphore) for symbol in TICKERS]

    results = await asyncio.gather(*tasks)
    # Filter out None results
    valid_results = [r for r in results if r is not None]

    if valid_results:
        df = pd.DataFrame(valid_results)
        print(f"\n--- Saving {len(valid_results)} validated records to multibaggers ---")
        repository.save_multibaggers(df)
        print("Seeding complete.")
    else:
        print("No valid data fetched. Database remains empty.")


if __name__ == "__main__":
    asyncio.run(seed_data())
