# tests/test_mock_history_correctness.py
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.data_layer.data_service import DataManager  # noqa: E402
from modules.data_layer.dq_gates import validate_dataframe  # noqa: E402


def test_mock_history_gating_behavior(monkeypatch):
    """Verify that _generate_mock_history is only triggered when USE_MOCK_HISTORY is True."""
    # Mock Ticker history call to raise an exception
    class BadTicker:
        def __init__(self, symbol):
            pass
        def history(self, *args, **kwargs):
            raise ValueError("yf fetch failed on purpose")

    monkeypatch.setattr("yfinance.Ticker", BadTicker)

    # 1. With USE_MOCK_HISTORY = False
    monkeypatch.setattr("modules.data_layer.data_service.USE_MOCK_HISTORY", False)
    dm = DataManager()
    with pytest.raises(ValueError):
        dm.fetch_history("FAILTICKER", period="1y")

    # 2. With USE_MOCK_HISTORY = True
    monkeypatch.setattr("modules.data_layer.data_service.USE_MOCK_HISTORY", True)
    dm2 = DataManager()
    df_mock = dm2.fetch_history("FAILTICKER", period="1y")
    assert not df_mock.empty
    assert df_mock.attrs.get("is_mock") is True


def test_dq_gates_preserves_mock_history_and_penalizes():
    """Verify validate_dataframe preserves data_quality_flags and penalizes data_quality by 50 points."""
    df = pd.DataFrame([
        {
            "symbol": "TEST1",
            "pe_ratio": 20.0,
            "roe": 15.0,
            "data_quality_flags": "mock_history",
        },
        {
            "symbol": "TEST2",
            "pe_ratio": 20.0,
            "roe": 15.0,
            "data_quality_flags": "",
        }
    ])

    df_validated = validate_dataframe(df)

    # TEST1 has mock_history, so it should have a score penalized by 50 points (max possible is 100)
    # Since there are no invalid/clamped fields, TEST2 should have 100, TEST1 should be 50
    test1_row = df_validated[df_validated["symbol"] == "TEST1"].iloc[0]
    test2_row = df_validated[df_validated["symbol"] == "TEST2"].iloc[0]

    assert "mock_history" in test1_row["data_quality_flags"]
    assert test1_row["data_quality"] == 50.0
    assert test2_row["data_quality"] == 100.0
