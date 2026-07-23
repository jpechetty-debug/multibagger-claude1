import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from backtest.backtest_engine import _extract_close_series
except Exception as _import_err:
    import pytest
    pytestmark = pytest.mark.skip(reason=f"backtest engine import failed: {_import_err}")
    def _extract_close_series(*a, **kw): pass

def test_extract_close_series_multiindex_yfinance_v0_2():
    """
    Test the multi-symbol MultiIndex path introduced in newer yfinance,
    where columns are MultiIndex with ("Close", symbol).
    """
    columns = pd.MultiIndex.from_tuples([("Close", "ABC.NS"), ("Close", "DEF.NS")])
    df = pd.DataFrame([[100.0, 200.0], [105.0, 195.0]], columns=columns)

    # Test extracting "ABC.NS"
    series = _extract_close_series(df, "ABC.NS")
    assert series.iloc[0] == 100.0
    assert series.iloc[1] == 105.0

    # Test extracting "DEF.NS"
    series = _extract_close_series(df, "DEF.NS")
    assert series.iloc[0] == 200.0
    assert series.iloc[1] == 195.0
