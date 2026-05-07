import asyncio
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest

from modules.adapters.yfinance import YFinanceProvider

class DummyExecutor:
    """Synchronous executor for testing async methods."""
    def submit(self, fn, *args, **kwargs):
        class Future:
            def result(self):
                return fn(*args, **kwargs)
        return Future()

@pytest.fixture
def dummy_executor():
    return DummyExecutor()

@pytest.mark.asyncio
async def test_yfinance_provider_fetch(dummy_executor):
    provider = YFinanceProvider(executor=dummy_executor)

    mock_info = {
        "currentPrice": 100.5,
        "regularMarketPrice": 100.5,
        "returnOnEquity": 0.15,
        "revenueGrowth": 0.10,
        "marketCap": 5000000000,
    }

    with patch("yfinance.Ticker") as mock_ticker_class:
        mock_ticker = MagicMock()
        mock_ticker.info = mock_info
        mock_ticker.financials = pd.DataFrame({"2023": [1000, 200]}, index=["Total Revenue", "Net Income"])
        mock_ticker.balance_sheet = pd.DataFrame({"2023": [5000, 2000]}, index=["Total Assets", "Total Liabilities"])
        mock_ticker.cash_flow = pd.DataFrame({"2023": [300]}, index=["Operating Cash Flow"])

        # Fast info fallback mock
        mock_ticker.fast_info = {"lastPrice": 100.5, "marketCap": 5000000000}

        mock_ticker_class.return_value = mock_ticker

        # Since the _run_executor_safe function runs in executor, and our DummyExecutor runs synchronously,
        # we can just await the fetch_fundamentals call (it will use asyncio's default executor since we don't
        # override loop.run_in_executor in test unless we explicitly patch it).
        # Actually, let's patch loop.run_in_executor to just call the function.

        with patch("asyncio.events.AbstractEventLoop.run_in_executor", new=lambda self, exc, func, *args: asyncio.sleep(0, result=func(*args))):
            data = await provider.fetch_fundamentals("RELIANCE.NS")

            assert data["symbol"] == "RELIANCE.NS"
            assert data["source"] == "yfinance"
            assert data["price"] == 100.5
            assert data["roe"] == 0.15
            assert data["sales_growth"] == 0.10
            assert "info" in data
            assert not data["financials"].empty
            assert not data["balance_sheet"].empty
            assert not data["cash_flow"].empty
