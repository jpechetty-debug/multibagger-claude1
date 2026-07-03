import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio

import pandas as pd
from screener import SovereignScreener

from db.repository import save_multibaggers


async def seed_one_stock(symbol="RELIANCE.NS"):
    print(f"Propagating {symbol} with Sprint 1 metrics...")
    screener = SovereignScreener()
    # Fetch data only for this stock
    data = await screener.get_stock_data(symbol)
    if data:
        # Convert to DataFrame as save_multibaggers expects
        df = pd.DataFrame([data])
        save_multibaggers(df)
        print(f"[SUCCESS] {symbol} populated in database.")
    else:
        print(f"[FAIL] Could not fetch data for {symbol}")


if __name__ == "__main__":
    asyncio.run(seed_one_stock())
