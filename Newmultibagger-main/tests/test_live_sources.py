import logging

from modules.data_service import get_data_manager

# Enable logging to see which source is processing
logging.basicConfig(level=logging.INFO)


def test_live_fetch():
    symbol = "SBIN.NS"
    print(f"Fetching fundamentals for {symbol}...")
    data = get_data_manager().fetch_fundamentals(symbol)

    if "error" in data:
        print(f"Error: {data['error']}")
    else:
        info = data.get("info", {})
        print(f"Success! Name: {info.get('longName')}, Price: {info.get('currentPrice')}")
        financials = data.get("financials")
        if financials is not None:
            print(f"Financials shape: {financials.shape}")
        else:
            print("Financials: None")

    print("\nFetching quarterly results...")
    timeline = get_data_manager().fetch_quarterly_results(symbol)
    print(f"Quarterly data points: {len(timeline)}")
    if timeline:
        print(f"Latest: {timeline[0]}")


if __name__ == "__main__":
    test_live_fetch()
