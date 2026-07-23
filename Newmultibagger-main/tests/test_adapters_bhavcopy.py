from datetime import datetime

import pandas as pd

from modules.adapters.nse_bhavcopy import (
    _dataframe_to_price_dict,
    _get_bhavcopy_dates,
    get_bhavcopy_price,
)


def test_get_bhavcopy_dates_skips_weekends():
    dates = _get_bhavcopy_dates(max_lookback=5)
    assert len(dates) == 5

    # Verify no weekends are in the output list.
    # Convert YYYYMMDD back to datetime and check weekday
    for d_str in dates:
        dt = datetime.strptime(d_str, "%Y%m%d")
        assert dt.weekday() < 5  # 0-4 is Mon-Fri

def test_dataframe_to_price_dict_filters_sctysrs():
    # Construct a mock DataFrame with mixed series (EQ, GB)
    df = pd.DataFrame({
        "TckrSymb": ["RELIANCE", "SGBJUN28"],
        "SctySrs": ["EQ", "GB"],
        "ClsPric": [2500.0, 14000.0],
        "TtlTradgVol": [1000000, 100]
    })

    price_dict = _dataframe_to_price_dict(df)

    # RELIANCE should be present
    assert "RELIANCE" in price_dict
    assert price_dict["RELIANCE"]["close"] == 2500.0

    # SGBJUN28 (Gold Bond) should be filtered out
    assert "SGBJUN28" not in price_dict

def test_dataframe_to_price_dict_fallback_columns():
    # Test alternate column names
    df = pd.DataFrame({
        "SYMBOL": ["TCS"],
        "SERIES": ["EQ"],
        "LastPric": [3000.0]
    })

    price_dict = _dataframe_to_price_dict(df)
    assert "TCS" in price_dict
    assert price_dict["TCS"]["last_price"] == 3000.0

def test_get_bhavcopy_price():
    prices = {
        "HDFCBANK": {"close": 1500.0},
        "INFY.NS": {"close": 1400.0}
    }

    assert get_bhavcopy_price(prices, "HDFCBANK") == 1500.0
    assert get_bhavcopy_price(prices, "HDFCBANK.NS") == 1500.0
    assert get_bhavcopy_price(prices, "INFY") == 1400.0
    assert get_bhavcopy_price(prices, "INFY.NS") == 1400.0
    assert get_bhavcopy_price(prices, "UNKNOWN") is None
