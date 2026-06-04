from modules.structured_logger import SovereignLogger, format_log_message
_log = SovereignLogger("modules.attribution").logger
def analyze_alpha_attribution(portfolio, universe):
    """
    Phase 36: Alpha Attribution / Factor Exposure Analysis.
    Determines the 'Source of Returns' by comparing Portfolio bets vs the Universe.

    Args:
        portfolio: List of stock dicts (The selected ones).
        universe: List of stock dicts (All scanned stocks).
    """
    _log.info(format_log_message("\n" + "=" * 50))
    _log.info(format_log_message("🧠 PHASE 36: ALPHA SOURCE ATTRIBUTION"))
    _log.info(format_log_message("=" * 50))

    if not portfolio or not universe:
        _log.info(format_log_message("Insufficient data for attribution."))
        return

    # Factors to analyze
    # We need to ensure these keys exist in the stock dicts.
    # If not, we rely on the 'factor_breakdown' stored during scoring.

    # We will assume 'Factors' dictionary is stored in the stock object now.

    # Calculate Averages
    portfolio_factors: dict[str, float] = {}
    universe_factors: dict[str, float] = {}

    # Heuristic: Aggregate the raw metrics or the scores?
    # Scores are better normalized.

    # We'll use the breakdown keys
    keys = ["Fundamentals", "Value", "Risk", "Momentum", "Smart_Money"]

    # 1. Compute Universe Averages
    uni_count = 0
    for stock in universe:
        factors = stock.get("Factors", {})
        if factors:
            uni_count += 1
            for k in keys:
                universe_factors[k] = universe_factors.get(k, 0) + factors.get(k, 0)

    if uni_count > 0:
        for k in keys:
            universe_factors[k] /= uni_count

    # 2. Compute Portfolio Averages
    port_count = 0
    for stock in portfolio:
        factors = stock.get("Factors", {})
        if factors:
            port_count += 1
            for k in keys:
                portfolio_factors[k] = portfolio_factors.get(k, 0) + factors.get(k, 0)

    if port_count > 0:
        for k in keys:
            portfolio_factors[k] /= port_count

    # 3. Compare and Attribute
    _log.info(format_log_message(f"{'Factor':<15} | {'Universe':<8} | {'Portfolio':<8} | {'Active Exposure':<15}"))
    _log.info(format_log_message("-" * 55))

    dominant_factor = "None"
    max_diff = 0

    for k in keys:
        u = universe_factors.get(k, 0)
        p = portfolio_factors.get(k, 0)
        diff = p - u
        diff_pct = (diff / u) * 100 if u > 0 else 0

        _log.info(format_log_message(f"{k:<15} | {u:>8.1f} | {p:>8.1f} | {diff_pct:>+8.1f}%"))

        if diff_pct > max_diff:
            max_diff = diff_pct
            dominant_factor = k

    _log.info(format_log_message("-" * 55))
    _log.info(format_log_message(f"🏆 PRIMARY ALPHA DRIVER: {dominant_factor.upper()}"))
    _log.info(format_log_message("=" * 50 + "\n"))
