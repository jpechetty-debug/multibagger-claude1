"""
Parquet Data Lake Manager.

Handles reading and writing historical tick/fundamental data using Polars for high performance.
This is Month 2 of the Sovereign Terminal master plan.
"""

import os
from pathlib import Path
from datetime import date
import polars as pl
from zoneinfo import ZoneInfo

# Ensure data lake directory exists
DATA_LAKE_PATH = Path("data/lake")
DATA_LAKE_PATH.mkdir(parents=True, exist_ok=True)

class ParquetLakeManager:
    """Manages the Parquet data lake for analytical queries."""
    
    def __init__(self, lake_path: Path = DATA_LAKE_PATH):
        self.lake_path = lake_path
        
    def _get_partition_path(self, symbol: str, data_type: str = "daily") -> Path:
        """Get the partition path for a specific symbol."""
        # e.g., data/lake/daily/RELIANCE.NS.parquet
        type_dir = self.lake_path / data_type
        type_dir.mkdir(exist_ok=True)
        return type_dir / f"{symbol}.parquet"
        
    def write_symbol_history(self, symbol: str, df: pl.DataFrame, data_type: str = "daily") -> None:
        """Write a symbol's historical data to Parquet."""
        path = self._get_partition_path(symbol, data_type)
        df.write_parquet(path)
        
    def read_symbol_history(self, symbol: str, data_type: str = "daily") -> pl.DataFrame:
        """Read a symbol's historical data from Parquet."""
        path = self._get_partition_path(symbol, data_type)
        if not path.exists():
            return pl.DataFrame()
        return pl.read_parquet(path)
        
    def query_all(self, data_type: str = "daily") -> pl.LazyFrame:
        """Scan all parquet files for a data type as a LazyFrame."""
        type_dir = self.lake_path / data_type
        if not type_dir.exists():
            return pl.LazyFrame()
        return pl.scan_parquet(type_dir / "*.parquet")
