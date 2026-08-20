import polars as pl
import pandas as pd
from modules.data_layer.parquet.lake_manager import ParquetLakeManager
from modules.target_engineering import build_training_targets

def load_evaluation_dataset(start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """Load evaluation dataset with forward_returns calculated on the fly."""
    from pathlib import Path
    daily_path = Path("data/lake/daily")
    if not daily_path.exists():
        return pd.DataFrame()
        
    dataset = pd.read_parquet(daily_path)
    
    if start_date:
        dataset = dataset[dataset["as_of_date"] >= start_date]
    if end_date:
        dataset = dataset[dataset["as_of_date"] <= end_date]
    
    from modules.scoring.ml_score import FEATURES
    available = ["symbol", "as_of_date", "price"] + FEATURES
    
    # Keep only available columns and convert to numeric
    dataset = dataset[[col for col in available if col in dataset.columns]].copy()
    for col in dataset.columns:
        if col not in ["symbol", "as_of_date"]:
            dataset[col] = pd.to_numeric(dataset[col], errors="coerce")
    
    if dataset.empty:
        return dataset
        
    if "price" in dataset.columns and "pit_price" not in dataset.columns:
        dataset = dataset.rename(columns={"price": "pit_price"})
        
    # Convert as_of_date to datetime if not already
    dataset["as_of_date"] = pd.to_datetime(dataset["as_of_date"])
    dataset = dataset.sort_values(["symbol", "as_of_date"])
    
    # Calculate 1-month forward return (approx 21 trading days) to ensure we have data in our 2-month dataset
    dataset["forward_price"] = dataset.groupby("symbol")["pit_price"].shift(-21)
    dataset["forward_return"] = (dataset["forward_price"] - dataset["pit_price"]) / dataset["pit_price"]
    
    dataset = dataset.dropna(subset=["forward_return"])
    return dataset
