from modules.structured_logger import SovereignLogger, format_log_message
_log = SovereignLogger("modules.portfolio.capital_simulator").logger
def simulate_capital_deployment(portfolio):
    """
    Phase 39: Capital Deployment Simulator.
    Tests if the strategy is scalable or just a 'Retail Toy'.

    Checks "Days to Liquidate" at different AUM levels:
    - ₹10 Lakh (Retail)
    - ₹1 Crore (HNI)
    - ₹10 Crore (Small Fund)

    Assumptions:
    - Participation Rate: 10% of Average Daily Volume (aggressive but standard).
    - If liquidating takes > 5 days, it's a "Liquidity Trap".
    """
    _log.info(format_log_message("\n" + "=" * 50))
    _log.info(format_log_message("🏦 PHASE 39: CAPITAL SCALABILITY STRESS TEST"))
    _log.info(format_log_message("=" * 50))

    if not portfolio:
        _log.info(format_log_message("No portfolio to test."))
        return

    scenarios = [
        {"name": "Retail Agent", "aum": 10_00_000},  # 10 Lakh
        {"name": "HNI Investor", "aum": 1_00_00_000},  # 1 Crore
        {"name": "Micro Fund", "aum": 10_00_00_000},  # 10 Crore
    ]

    _log.info(format_log_message(f"{'Scenario':<15} | {'AUM':<12} | {'Max Days to Exit':<18} | {'Status':<15}"))
    _log.info(format_log_message("-" * 65))

    for scen in scenarios:
        name = scen["name"]
        aum = scen["aum"]
        max_days = 0
        bottleneck_stock = "None"

        for stock in portfolio:
            weight = stock.get("Target_Weight%", 10) / 100
            position_size = aum * weight

            # Get Avg Volume (Value)
            # We assume 'Avg_Volume_10D' is in Shares. We need Value.
            # If not available, we estimate.

            avg_vol_shares = stock.get("Avg_Volume_10D", 0)
            price = stock.get("Price", 0)

            if avg_vol_shares == 0 or price == 0:
                continue

            avg_daily_value = avg_vol_shares * price

            # Max we can sell per day = 10% of ADV
            max_sell_per_day = avg_daily_value * 0.10

            days = 999 if max_sell_per_day == 0 else position_size / max_sell_per_day

            if days > max_days:
                max_days = days
                bottleneck_stock = stock.get("Symbol", "Unknown")

        # Determine Status
        status = "✅ Liquid"
        if max_days > 20:
            status = "❌ IMPOSSIBLE"
        elif max_days > 5:
            status = "⚠️ Illiquid"

        aum_val = float(scen.get("aum", 0))
        _log.info(format_log_message(f"{name:<15} | ₹{aum_val / 100000:>4.0f}L       | {max_days:>5.1f} Days ({bottleneck_stock}) | {status:<15}"))

    _log.info(format_log_message("-" * 65))
    _log.info(format_log_message("Note: 'Days to Exit' assumes max 10% participation of Daily Volume."))
    _log.info(format_log_message("=" * 50 + "\n"))
