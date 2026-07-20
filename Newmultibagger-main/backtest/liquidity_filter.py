"""
Liquidity Filter
----------------
Ensures backtests only trade stocks that were actually liquid enough at the time.
Prevents "Ghost Gains" from trading illiquid penny stocks in simulation.

Criteria:
1. Min Price > 10 (Avoid penny stocks with huge spreads)
2. Avg Daily Volume (ADV) * Price > Min Turnover (e.g. 50 Lakhs)
3. Trading Days > 90% of business days (observed market sessions; avoid suspended stocks)
"""
from core.observability.logger import get_logger
_log = get_logger("backtest.liquidity_filter")


class LiquidityFilter:
    def __init__(
        self,
        min_price: float = 10.0,
        min_turnover: float = 5_000_000.0,
        min_trading_day_ratio: float = 0.90,
    ):
        self.min_price = min_price
        self.min_turnover = min_turnover
        self.min_trading_day_ratio = min_trading_day_ratio

    def filter(self, universe_data):
        """
        Filters a list of stock data dicts.

        Args:
            universe_data (list): List of dicts containing ``Symbol``, ``Price``,
                ``Volume``, ``Trading_Days``, and ``Business_Days``. The two day
                counts must cover the same historical window.

        Returns:
            list: Filtered list of dicts.
        """
        liquid_universe = []
        rejected = 0

        for stock in universe_data:
            try:
                price = float(stock.get("Price", 0))
                volume = float(stock.get("Volume", 0))
                trading_days = int(stock.get("Trading_Days", 0))
                business_days = int(stock.get("Business_Days", 0))
            except (TypeError, ValueError):
                rejected += 1
                continue

            turnover = price * volume

            # 1. Price Check
            if price < self.min_price:
                rejected += 1
                continue

            # 2. Turnover Check
            if turnover < self.min_turnover:
                rejected += 1
                continue

            # 3. Trading-day coverage check. Require strictly more than 90%
            # coverage so suspended or intermittently quoted stocks cannot pass.
            if (
                business_days <= 0
                or trading_days < 0
                or trading_days / business_days <= self.min_trading_day_ratio
            ):
                rejected += 1
                continue

            liquid_universe.append(stock)

        _log.info(f"Liquidity Filter: Passed {len(liquid_universe)} / {len(universe_data)} (Rejected {rejected})")
        return liquid_universe
