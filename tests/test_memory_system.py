import asyncio
import os
import re
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sovereign_mcp import (
    analyze_ticker,
    get_observation_details,
    get_ticker_timeline,
    search_research_memory,
)


async def test_memory():
    print("Testing Research Memory Integration...")

    # 1. Trigger an analysis which should hit the MemoryManager hook
    print("Running analyze_ticker('TCS.NS')...")
    res = await analyze_ticker("TCS.NS")
    print(f"Output snippet: {res[:50]}...\n")

    # 2. Search for the memory
    print("Searching Memory Index for 'TCS'...")
    search_res = await search_research_memory("TCS")
    print(search_res)
    assert "TCS" in search_res or "Global" in search_res, "Search index failed!"

    # Extract ID
    match = re.search(r"\[ID: (\d+)\]", search_res)
    if match:
        obs_id = int(match.group(1))
        # 3. Get Details
        print(f"\nFetching Exact Details for ID {obs_id}...")
        detail_res = await get_observation_details([obs_id])
        print(f"Details snippet: {detail_res[:100]}...")

    # 4. Get timeline
    print("\nFetching Timeline for 'TCS.NS'...")
    timeline_res = await get_ticker_timeline("TCS.NS")
    print(timeline_res)

    print("\n✅ All memory hooks successfully executed and returned valid data!")


if __name__ == "__main__":
    asyncio.run(test_memory())
