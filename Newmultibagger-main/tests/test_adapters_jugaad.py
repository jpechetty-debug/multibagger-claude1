import pandas as pd
from datetime import date
from unittest.mock import patch
from modules.adapters.jugaad import get_jugaad_history

def test_jugaad_rejects_bse_symbols():
    # .BO symbols should return empty dataframe immediately
    df = get_jugaad_history("RELIANCE.BO", date(2023, 1, 1), date(2023, 1, 5))
    assert df.empty

@patch("modules.adapters.jugaad.stock_df")
def test_jugaad_strips_ns_suffix(mock_stock_df):
    mock_stock_df.return_value = []
    get_jugaad_history("TCS.NS", date(2023, 1, 1), date(2023, 1, 5))
    
    # Verify stock_df was called with just "TCS"
    mock_stock_df.assert_called_once()
    assert mock_stock_df.call_args[1]["symbol"] == "TCS"

@patch("modules.adapters.jugaad.stock_df")
def test_jugaad_standardizes_schema(mock_stock_df):
    # Mock response typical of jugaad-data
    mock_stock_df.return_value = [
        {
            "DATE": "02-Jan-2023",
            "SERIES": "EQ",
            "OPEN": 2500.0,
            "HIGH": 2550.0,
            "LOW": 2490.0,
            "PREV. CLOSE": 2495.0,
            "ltp": 2540.0,
            "close": 2545.0,
            "vwap": 2530.0,
            "52W H": 2800.0,
            "52W L": 2000.0,
            "VOLUME": 1000000,
            "VALUE": 2530000000.0,
            "No of trades": 50000
        }
    ]
    
    df = get_jugaad_history("INFY", date(2023, 1, 2), date(2023, 1, 2))
    
    assert not df.empty
    
    # Assert standard columns exist
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    
    # Assert values mapped correctly
    assert df.iloc[0]["Open"] == 2500.0
    assert df.iloc[0]["High"] == 2550.0
    assert df.iloc[0]["Low"] == 2490.0
    assert df.iloc[0]["Close"] == 2545.0
    assert df.iloc[0]["Volume"] == 1000000
    
    # Assert index is a DatetimeIndex
    assert isinstance(df.index, pd.DatetimeIndex)
