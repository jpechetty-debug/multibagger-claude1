import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.path.abspath('.'))

from modules.quarterly_results import get_quarterly_timeline

async def test():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE.NS"
    print(f"Testing quarterly timeline for {symbol}...")
    try:
        result = await get_quarterly_timeline(symbol)
        print("Success!")
        print(f"Keys: {list(result.keys())}")
        print(f"Quarters: {len(result.get('quarters', []))}")
        if result.get('alerts'):
            print(f"Alerts: {result['alerts']}")
    except Exception as e:
        print(f"CRASH: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
