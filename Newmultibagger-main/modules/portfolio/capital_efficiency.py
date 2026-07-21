from core.observability.logger import get_logger
_log = get_logger(__name__)

def analyze_capital_efficiency(stock_data):
    """
    Phase 28: Capital Efficiency Ranking.
    Distinguishes 'Compounders' from 'Capital Destroyers'.

    Returns:
        roic (float): Estimated ROIC %.
        efficiency_status (str): "Compounder", "Standard", "Destroyer".
        efficiency_score (int): Bonus/Penalty (+5 to -5).
    """
    try:
        # 1. Try to get ROIC from data if available (yfinance sometimes has returnOnEquity, returnOnAssets, but ROIC is scarce)
        # We will attempt to calculate or use proxies.

        # Proxy: ROIC ~ ROE * (1 - Debt/Asset) + RODA * (Debt/Asset)?
        # Simpler: Use ROE if Debt is Low. If Debt is High, ROE is inflated.

        roe = stock_data.get("ROE%", 0)
        debt_equity = stock_data.get("Debt_Equity", 0)
        profit_margin = stock_data.get("Profit_Margin%", 0)

        # Estimate Invested Capital efficiency roughly
        # High ROE + Low Debt = True Compounding
        # High ROE + High Debt = Financial Engineering (Leveraged Returns)

        # Let's adjust ROE for Debt to get a "Unlevered Return" proxy
        # Adjusted ROE = ROE / (1 + Debt_Equity) * (something)
        # Actually, let's just use strict criteria.

        score = 0
        status = "Standard"

        # Criteria for COMPOUNDER (Value Creator)
        # ROE > 15% AND Debt/Equity < 0.5 AND Margins > 10%
        if roe > 15 and debt_equity < 0.5 and profit_margin > 10:
            status = "Compounder 💎"
            score = 5
        elif roe > 20 and debt_equity < 1.0:
            status = "Compounder (Lev)"
            score = 3

        # Criteria for CAPITAL DESTROYER
        # ROE < 8% (Below Cost of Capital in India)
        elif roe < 8:
            status = "Capital Destroyer 🗑️"
            score = -5
        elif roe < 12:
            status = "Sub-Par"
            score = -2

        return roe, status, score

    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return 0, "Error", 0


class YieldRedirectController:
    """
    Manages uninvested capital when the Allocation Governor (Optimizer) throttles
    market exposure due to regime constraints.
    Redirects excess cash into a safe yield proxy (e.g., Liquid BeES or flat cash rate).
    """

    # Default annualized yield for parked cash (e.g., Liquid BeES ~ 6.5%)
    ANNUAL_YIELD = 0.065

    def __init__(self, proxy_symbol="LIQUIDBEES.NS"):
        self.proxy_symbol = proxy_symbol
        self.parked_cash = 0.0

    def sweep_excess_cash(self, cash_amount):
        """
        Takes excess cash from the portfolio optimization process and parks it.
        """
        if cash_amount > 0:
            self.parked_cash += cash_amount
            _log.info(f"Swept ₹{cash_amount:,.2f} into Yield Redirect ({self.proxy_symbol}). Total Parked: ₹{self.parked_cash:,.2f}")
        return self.parked_cash

    def release_cash(self, required_amount):
        """
        Releases cash from the yield proxy back to the equity pool.
        """
        if required_amount <= 0:
            return 0.0

        released = min(required_amount, self.parked_cash)
        self.parked_cash -= released
        _log.info(f"Released ₹{released:,.2f} from Yield Redirect. Remaining Parked: ₹{self.parked_cash:,.2f}")
        return released

    def calculate_yield(self, days):
        """
        Calculates the interest earned on the currently parked cash over a period of days.
        """
        if self.parked_cash <= 0 or days <= 0:
            return 0.0

        # Simple interest approximation for short periods
        daily_rate = self.ANNUAL_YIELD / 365.0
        earned_yield = self.parked_cash * daily_rate * days

        _log.info(f"Yield Redirect generated ₹{earned_yield:,.2f} over {days} days on ₹{self.parked_cash:,.2f} parked.")
        return earned_yield
