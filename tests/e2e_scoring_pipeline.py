# tests/e2e_scoring_pipeline.py
"""
Sovereign Terminal — End-to-End Integration Test
Verifies the full pipeline: Data Fetch -> Scoring -> Result Construction.
Uses a mock DataManager to avoid live API calls during CI.
"""
import pytest
import asyncio
import pandas as pd
from datetime import datetime
from modules.data_service import DataManager
from scripts.internal.screener import get_stock_data
from modules.scoring import calculate_institutional_score

class MockDataManager(DataManager):
    """Overrides DataManager to return deterministic mock data."""
    async def async_fetch_fundamentals(self, symbol: str):
        return {
            "symbol": symbol,
            "source": "mock",
            "price": 100.0,
            "info": {
                "marketCap": 10000000000,
                "trailingPE": 20.0,
                "returnOnEquity": 0.15,
                "debtToEquity": 0.5,
                "revenueGrowth": 0.20,
                "sector": "Technology",
                "industry": "Software"
            },
            "financials": pd.DataFrame(),
            "balance_sheet": pd.DataFrame(),
            "cash_flow": pd.DataFrame()
        }

    async def async_fetch_history(self, symbol: str, period: str = "1y"):
        # Create 252 days of mock history
        dates = pd.date_range(end=datetime.now(), periods=252)
        df = pd.DataFrame({
            "Close": [100.0 + i*0.1 for i in range(252)],
            "High": [101.0 + i*0.1 for i in range(252)],
            "Low": [99.0 + i*0.1 for i in range(252)],
            "Volume": [1000000 for _ in range(252)]
        }, index=dates)
        return df

@pytest.mark.asyncio
async def test_full_scoring_pipeline_e2e():
    """Verify that a symbol can pass through the entire fetch-and-score pipe."""
    symbol = "TCS.NS"
    mock_dm = MockDataManager(max_concurrency=1)
    
    # 1. Fetch
    stock_data = await get_stock_data(symbol, dm=mock_dm, include_quarterly=False)
    
    assert stock_data["Symbol"] == symbol
    assert stock_data["Price"] > 0
    assert stock_data["Data_Source"] == "mock"
    
    # 2. Score
    score_payload = calculate_institutional_score(stock_data, market_regime="BULL")
    
    assert "total_score" in score_payload
    assert "checklist_score" in score_payload
    assert score_payload["total_score"] > 0
    
    # 3. Final Result construction
    score = float(score_payload.get("total_score", 0.0))
    assert 0 <= score <= 100
    
    print(f"\nE2E Pipeline Success for {symbol}: Score={score}")

if __name__ == "__main__":
    # Manual run support
    asyncio.run(test_full_scoring_pipeline_e2e())
