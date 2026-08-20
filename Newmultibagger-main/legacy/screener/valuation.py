"""
Trade setup and risk parameter calculations.

Extracted from scripts/internal/screener.py.
"""


def calculate_trade_setup(stock):
    """Calculates standard Buy Below, Stop Loss, and Target prices."""
    if not stock or "Price" not in stock:
        return stock

    cmp = stock["Price"]
    if cmp and cmp > 0:
        stock["Buy_Below"] = round(cmp * 1.02, 1)

        atr_sl = stock.get("Stop_Loss_ATR")
        if atr_sl and atr_sl > 0:
            stock["Stop_Loss"] = round(atr_sl, 1)
        else:
            stock["Stop_Loss"] = round(cmp * 0.90, 1)

        stock["Target_1"] = round(cmp * 1.25, 1)

    return stock


def calculate_risk_params(price, atr, capital=100000, risk_pct=0.02):
    """Calculate position size and stop loss from ATR."""
    if not price or not atr or price <= 0 or atr <= 0:
        return None, None

    stop_loss = price - (2 * atr)
    risk_per_share = price - stop_loss
    if risk_per_share <= 0:
        return round(stop_loss, 2), 0

    risk_amount = capital * risk_pct
    qty = int(risk_amount / risk_per_share)

    return round(stop_loss, 2), qty
