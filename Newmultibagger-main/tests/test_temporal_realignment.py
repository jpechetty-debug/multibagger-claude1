"""Tests for Phase 6.2: Temporal Realignment Engine."""

import pandas as pd

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.data_layer.temporal_realignment import TemporalRealignmentEngine

def test_temporal_realignment_engine_applies_lag():
    """Verify that the engine applies the strict publishing lag correctly."""

    # 45-day lag
    engine = TemporalRealignmentEngine(publishing_lag_days=45)

    df = pd.DataFrame({
        "symbol": ["A", "B", "C"],
        "source_updated_at": ["2023-03-31", "2023-06-30", "2023-12-31"]
    })

    aligned_df = engine.align_fundamentals(df, date_column="source_updated_at")

    # Expected dates after adding 45 days
    expected_dates = pd.Series(pd.to_datetime(["2023-05-15", "2023-08-14", "2024-02-14"]))

    pd.testing.assert_series_equal(
        aligned_df["source_updated_at"],
        expected_dates,
        check_names=False
    )

def test_temporal_realignment_engine_missing_column():
    """Verify it returns the original dataframe gracefully if column is missing."""
    engine = TemporalRealignmentEngine(publishing_lag_days=45)

    df = pd.DataFrame({
        "symbol": ["A", "B"],
        "price": [100, 200]
    })

    aligned_df = engine.align_fundamentals(df, date_column="as_of_date")
    pd.testing.assert_frame_equal(df, aligned_df)

def test_temporal_realignment_engine_empty_df():
    """Verify it handles empty dataframes."""
    engine = TemporalRealignmentEngine(publishing_lag_days=45)

    df = pd.DataFrame(columns=["symbol", "as_of_date"])
    aligned_df = engine.align_fundamentals(df, date_column="as_of_date")

    assert aligned_df.empty
