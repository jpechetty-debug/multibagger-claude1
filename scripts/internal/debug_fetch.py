import asyncio
import sys
import os

# Add root project and Newmultibagger-main to sys.path
root = os.getcwd()
sys.path.insert(0, root)

import screener
from modules.data_service import DataManager

async def debug_fetch(symbol):
    dm = DataManager()
    print(f"--- Debugging Fetch for {symbol} ---")
    res = await dm.async_fetch_fundamentals(symbol)
    print(f"Result: {res}")
    
    if res.get('_fetch_error'):
        print(f"Error Detail: {res.get('_fetch_error_detail')}")

if __name__ == "__main__":
    asyncio.run(debug_fetch("RELIANCE.NS"))
