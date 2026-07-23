# modules/market_data.py
# Legacy shim — re-exports MarketDataProvider so that test patches targeting
# modules.market_data.MarketDataProvider continue to work after the module
# was moved to modules/data_layer/data_service.py.

import yfinance as yf  # noqa: F401 — re-exported so patch targets resolve

from modules.data_layer.data_service import (  # noqa: F401
    MarketDataProvider,
    get_data_manager,
)
