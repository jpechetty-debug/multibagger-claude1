import math

import pandas as pd
from core.observability.logger import get_logger
_log = get_logger("modules.portfolio.execution")


def generate_broker_orders(portfolio, total_capital=1000000, broker="ZERODHA"):
    """
    Phase 41: Live Execution Bridge.
    Converts the Model Portfolio into actionable Broker Order files.

    Args:
        portfolio (list): List of stock dicts with 'Target_Weight%'.
        total_capital (float): Total capital to deploy (default ₹10L).
        broker (str): "ZERODHA", "ANGEL", "UPSTOX".

    Returns:
        filename (str): Path to the generated CSV.
    """
    _log.info("\n" + "=" * 50)
    _log.info(f"📠 PHASE 41: GENERATING {broker} ORDER BASKET (Cap: ₹{total_capital / 100000}L)")
    _log.info("=" * 50)

    orders = []

    for stock in portfolio:
        symbol = stock.get("Symbol", "")
        weight = stock.get("Target_Weight%", 0) / 100
        price = stock.get("Price", 0)

        if price == 0:
            continue

        # 1. Calculate Quantity
        target_value = total_capital * weight
        quantity = math.floor(target_value / price)

        if quantity == 0:
            continue

        # 2. Format for Zerodha (Kite)
        # Format: instrument, trans_type, qty, price, product, order_type
        # Example: INFY, BUY, 10, 0, CNC, MARKET

        if broker == "ZERODHA":
            orders.append(
                {
                    "instrument": symbol,  # Might need exchange prefix like 'NSE:RELIANCE'
                    "trans_type": "BUY",
                    "qty": quantity,
                    "price": 0,  # Market Order
                    "product": "CNC",  # Delivery
                    "order_type": "MARKET",
                }
            )

    if not orders:
        _log.info("No orders generated (Check Capital scaling).")
        return None

    df = pd.DataFrame(orders)

    # Save
    filename = f"orders_{broker.lower()}.csv"
    df.to_csv(
        filename, index=False, header=False
    )  # Kite basket often needs no header or specific header

    _log.info(f"ORDERS GENERATED: {len(orders)} Trades")
    _log.info(f"Saved to: {filename}")
    _log.info(f"Action: Upload this file to {broker} Basket Order tool.")
    _log.info("=" * 50 + "\n")

    return filename
