import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath('.'))

from modules.data_service import data_manager

async def test():
    symbols = ["RELIANCE.NS", "TCS.NS", "INFY.NS"]
    print(f"Fetching for {symbols}...")
    results = await data_manager.fetch_batch(symbols)
    for s, d in results.items():
        print(f"{s}: price={d.get('price')}, error={d.get('error')}, keys={list(d.keys())}")

if __name__ == "__main__":
    asyncio.run(test())
