"""Tests for Phase 6.1: Survivorship Bias Adjustment Rig."""

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.backtest_engine import VectorBTEngine

def test_survivorship_splicing_delisted_stock():
    """Verify that the engine splices delisted stock data when yfinance fails."""
    engine = VectorBTEngine()

    # Mock yfinance to return empty for "DELISTED"
    with patch("backtest.backtest_engine.yf.download") as mock_yf:
        mock_yf.return_value = pd.DataFrame()

        # Mock SurvivorshipAdjustedLoader to return mock delisted data
        mock_delisted_df = pd.DataFrame({
            "Date": ["2019-01-01", "2019-02-01"],
            "Close": [100.0, 50.0]
        })

        engine._survivorship_loader.load_delisted_data = MagicMock(return_value=mock_delisted_df)
        engine._survivorship_loader.get_universe = MagicMock(return_value=["DELISTED.NS"])

        # We need to stub db call to return a pit feature for "DELISTED" so fold continues
        with patch("backtest.backtest_engine.pd.read_sql_query") as mock_db:
            mock_db.return_value = pd.DataFrame({
                "symbol": ["DELISTED.NS", "DELISTED.NS"],
                "as_of_date": ["2018-12-31", "2019-01-31"],
                "score": [90.0, 80.0]
            })

            # Run a dummy backtest (it will likely fail due to insufficient data for full strategy,
            # but we just want to ensure `load_delisted_data` is called)
            # Actually, `run_walk_forward_strategy_backtest` requires > min_train_periods.
            # Let's just test that the splicing loop works by triggering it.

            result = engine.run_walk_forward_strategy_backtest(
                symbols=["DELISTED"],
                min_train_periods=1
            )

            # The exact result doesn't matter, we just verify the call was made
            engine._survivorship_loader.load_delisted_data.assert_called_with("DELISTED.NS")

def test_survivorship_splicing_ignores_active_stocks():
    """Verify it skips loader if yfinance successfully returns data."""
    engine = VectorBTEngine()

    with patch("backtest.backtest_engine.yf.download") as mock_yf:
        mock_yf.return_value = pd.DataFrame({
            "Close": [100.0, 105.0]
        }, index=pd.to_datetime(["2023-01-01", "2023-02-01"]))

        engine._survivorship_loader.load_delisted_data = MagicMock()

        with patch("backtest.backtest_engine.pd.read_sql_query") as mock_db:
            mock_db.return_value = pd.DataFrame()

            engine.run_walk_forward_strategy_backtest(["RELIANCE"])

            engine._survivorship_loader.load_delisted_data.assert_not_called()
