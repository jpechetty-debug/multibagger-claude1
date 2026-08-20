"""
Feature Store API.

Provides point-in-time correct features built from the Parquet data lake.
Delegates heavy processing to DuckDB/Polars.
"""

from datetime import date
from typing import Any
import polars as pl

from modules.data_layer.parquet.lake_manager import ParquetLakeManager
from modules.domain.company import CompanySnapshot

class FeatureStore:
    """
    Manages offline analytical feature computation and retrieval.
    """
    
    def __init__(self, lake: ParquetLakeManager):
        self.lake = lake
        
    def get_features_for_snapshot(self, snapshot: CompanySnapshot) -> dict[str, Any]:
        """
        Compute or retrieve pre-computed features for a specific CompanySnapshot.
        Guarantees no lookahead bias by strictly respecting snapshot.as_of_date.
        """
        symbol = snapshot.symbol
        as_of_date = snapshot.as_of_date
        
        # In a full implementation, this would query the Parquet lake for historical
        # data exactly up to as_of_date, run cross-sectional normalization via DuckDB/Polars,
        # and return the feature vector.
        
        # For now, we return an empty dictionary which will be populated as we migrate
        # the feature_factory logic here.
        return {}
        
    def generate_training_dataset(self, symbols: list[str], start_date: date, end_date: date) -> pl.DataFrame:
        """
        Generate a point-in-time correct dataset for model training.
        Strictly excludes the holdout period (2018-01-01 to 2020-12-31).
        """
        HOLDOUT_START = date(2018, 1, 1)
        HOLDOUT_END = date(2020, 12, 31)
        
        # We query all available parquet files as a LazyFrame
        lf = self.lake.query_all("daily")
        
        # Apply date filters and holdout exclusion
        # We assume the schema has 'as_of_date' as a string 'YYYY-MM-DD' or date object.
        # Polars str.to_date is safe if it's strings, otherwise direct comparison.
        # To be safe, we'll cast start_date, end_date to strings for comparison.
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        holdout_start_str = HOLDOUT_START.strftime("%Y-%m-%d")
        holdout_end_str = HOLDOUT_END.strftime("%Y-%m-%d")

        dataset = (
            lf
            .filter(pl.col("symbol").is_in(symbols))
            .filter(pl.col("as_of_date") >= start_str)
            .filter(pl.col("as_of_date") <= end_str)
            .filter(
                (pl.col("as_of_date") < holdout_start_str) | 
                (pl.col("as_of_date") > holdout_end_str)
            )
            .collect()
        )
        
        return dataset
