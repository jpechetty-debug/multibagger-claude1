import pandas as pd
import logging
from core.observability.logger import get_logger

_log = get_logger("data_layer.temporal_realignment")

class TemporalRealignmentEngine:
    """
    Module 6.2: PIT Temporal Realignment Engine
    Enforces a strict lag on fundamental data (e.g., EPS, ROE) to ensure no
    look-ahead bias exists during backtesting. Financial results are typically
    published weeks after the actual quarter-end date.
    """

    def __init__(self, publishing_lag_days: int = 45):
        """
        Args:
            publishing_lag_days: The number of days to lag the fundamental data
                                 from the actual end of the reporting period.
        """
        self.publishing_lag_days = publishing_lag_days

    def align_fundamentals(self, df: pd.DataFrame, date_column: str = "as_of_date") -> pd.DataFrame:
        """
        Applies the publishing lag to the specified date column.
        
        Args:
            df: DataFrame containing fundamental data.
            date_column: The column representing the reporting period end date.
            
        Returns:
            A new DataFrame with the temporally realigned 'as_of_date'.
        """
        if df is None or df.empty:
            return df

        if date_column not in df.columns:
            _log.warning(f"Date column '{date_column}' not found. Cannot apply temporal realignment.")
            return df

        aligned_df = df.copy()
        
        # Convert to datetime safely
        aligned_df[date_column] = pd.to_datetime(aligned_df[date_column], errors="coerce")
        
        # Apply strict publishing lag to prevent look-ahead bias
        aligned_df[date_column] = aligned_df[date_column] + pd.Timedelta(days=self.publishing_lag_days)
        
        _log.info(f"Temporal Realignment Engine: Applied {self.publishing_lag_days}-day publishing lag to {len(aligned_df)} rows.")
        
        return aligned_df
