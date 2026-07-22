from core.observability.logger import get_logger
_log = get_logger("modules.risk.stress_test")
def _build_weights(portfolio_stocks, weights=None):
    if weights:
        return weights
    if not portfolio_stocks:
        return {}
    return {s["Symbol"]: 1.0 / len(portfolio_stocks) for s in portfolio_stocks}


import pandas as pd

def _calculate_1yr_beta(symbol: str) -> float | None:
    try:
        from modules.data_service import get_data_manager
        from modules.data_utils import run_coroutine_sync

        async def fetch_data():
            stock_df = await get_data_manager().async_fetch_history(symbol)
            bench_df = await get_data_manager().async_fetch_history("^NSEI")
            return stock_df, bench_df

        stock_df, bench_df = run_coroutine_sync(fetch_data())

        if stock_df is None or bench_df is None or stock_df.empty or bench_df.empty:
            return None

        stock_df = stock_df.tail(252)
        bench_df = bench_df.tail(252)

        stock_ret = stock_df["Close"].pct_change().dropna()
        bench_ret = bench_df["Close"].pct_change().dropna()

        df = pd.DataFrame({"stock": stock_ret, "bench": bench_ret}).dropna()

        if len(df) < 50:
            return None

        cov = df.cov().iloc[0, 1]
        var = df["bench"].var()

        if var == 0:
            return None

        return float(cov / var)
    except Exception as e:
        return None

def _estimate_portfolio_beta(portfolio_stocks, weights=None):
    if not portfolio_stocks:
        return 1.0

    use_weights = _build_weights(portfolio_stocks, weights)
    total_beta = 0.0
    total_weight = 0.0

    for stock in portfolio_stocks:
        sym = stock["Symbol"]
        wt = use_weights.get(sym, 0.0)

        # 1-yr rolling regression (Phase 20)
        beta = _calculate_1yr_beta(sym)

        # Fallback to heuristic if regression fails
        if beta is None:
            beta = 1.0
            sec = stock.get("Sector", "Unknown")
            if sec in ["Technology", "Realty", "Metals"]:
                beta += 0.3
            if sec in ["FMCG", "Utilities", "Pharma"]:
                beta -= 0.2

            atr = stock.get("ATR", 0)
            price = stock.get("Price", 1)
            if price > 0:
                vol = atr / price
                if vol > 0.03:
                    beta += 0.2
                if vol < 0.015:
                    beta -= 0.1

        total_beta += beta * wt
        total_weight += wt

    return total_beta / total_weight if total_weight > 0 else 1.0


def run_stress_test(portfolio_stocks, weights=None):
    """
    Phase 20: Risks Management Stress Testing.
    Simulates how the portfolio would behave in historical crash scenarios.

    scenarios = {
        "2008 Global Financial Crisis": -0.55,
        "2020 Covid Crash": -0.38,
        "2022 Tech Bear Market": -0.22,
        "Standard Correction": -0.10
    }
    """
    _log.info("\n" + "=" * 50)
    _log.info("🌪️  PHASE 20: PORTFOLIO STRESS TEST (CRASH SIMULATION)")
    _log.info("=" * 50)

    if not portfolio_stocks:
        _log.info("Empty portfolio.")
        return

    # 1. Calculate Portfolio Beta
    # We estimate Beta based on Sector and Volatility (ATR)
    # High Beta (>1.2) = Aggressive
    # Low Beta (<0.8) = Defensive

    portfolio_beta = _estimate_portfolio_beta(portfolio_stocks, weights)

    _log.info(f"Portfolio Beta (Estimated): {portfolio_beta:.2f}")
    if portfolio_beta > 1.3:
        _log.warning("⚠️  Risk Profile: AGGRESSIVE (High Volatility)")
    elif portfolio_beta < 0.8:
        _log.info("🛡️  Risk Profile: DEFENSIVE (Low Volatility)")
    else:
        _log.info("⚖️  Risk Profile: BALANCED")

    _log.info("-" * 50)
    _log.info(f"{'Scenario':<30} | {'Market Drop':<12} | {'Est. Portfolio Impact':<20}")
    _log.info("-" * 50)

    scenarios = [
        ("Correction (Standard)", -0.10),
        ("2022 Inflation Bear", -0.22),
        ("2020 Covid Flash Crash", -0.38),
        ("2008 Financial Crisis", -0.55),
    ]

    for name, drop in scenarios:
        # Impact = Beta * Market Drop
        # But we add a 'Alpha Cushion'? No, in a crash, correlation goes to 1.
        # Often High Beta falls MORE than Beta implies during panic.

        impact = drop * portfolio_beta

        # formatting
        mkt_lbl = f"{drop * 100:.0f}%"
        port_lbl = f"{impact * 100:.1f}%"

        # Color code (text based)
        emoji = "🩸" if impact < -0.3 else ("🔻" if impact < -0.15 else "📉")

        _log.info(f"{name:<30} | {mkt_lbl:<12} | {port_lbl:<20} {emoji}")

    _log.info("=" * 50 + "\n")



# ── run_adversarial_scenario_replay ──────────────────────────────────────────
# Full implementation matching tests/test_risk_scenario_replay.py contract.

def run_adversarial_scenario_replay(portfolio_stocks, base_vix=18.0, weights=None, benchmark_returns=None):
    """Run 3 adversarial scenarios against a portfolio and return worst-case analysis.

    Args:
        portfolio_stocks: List of dicts with Symbol, Sector, Price, ATR.
        base_vix: Current VIX level (default 18.0).
        weights: Optional {symbol: weight} dict; equal-weight if None.
        benchmark_returns: Unused, kept for API compatibility.

    Returns:
        Dict with keys: base_vix, portfolio_beta, scenarios (list of 3),
        worst_case (scenario with highest estimated_drawdown_pct).
    """
    portfolio_beta = _estimate_portfolio_beta(portfolio_stocks, weights)

    # ── 3 fixed adversarial scenarios ────────────────────────────────────────
    # Scenario definitions scale with base_vix for realism.
    vix_stress_mult = 1.0 + (base_vix - 15.0) / 30.0   # higher VIX → worse scenarios

    scenarios = [
        {
            "name":                 "Flash Crash",
            "gap_down_pct":         0.08 * vix_stress_mult,
            "slippage_bps":         80 * vix_stress_mult,
            "correlation_spike":    0.70,
            "vix":                  base_vix * 1.5,
            "estimated_drawdown_pct": round(
                0.08 * portfolio_beta * vix_stress_mult * 100, 2
            ),
        },
        {
            "name":                 "Liquidity Freeze",
            "gap_down_pct":         0.12 * vix_stress_mult,
            "slippage_bps":         200 * vix_stress_mult,
            "correlation_spike":    0.88,
            "vix":                  base_vix * 2.0,
            "estimated_drawdown_pct": round(
                0.15 * portfolio_beta * vix_stress_mult * 100, 2
            ),
        },
        {
            "name":                 "Regime Collapse",
            "gap_down_pct":         0.05 * vix_stress_mult,
            "slippage_bps":         50 * vix_stress_mult,
            "correlation_spike":    0.60,
            "vix":                  base_vix * 1.2,
            "estimated_drawdown_pct": round(
                0.06 * portfolio_beta * vix_stress_mult * 100, 2
            ),
        },
    ]

    worst_case = max(scenarios, key=lambda s: s["estimated_drawdown_pct"])

    return {
        "base_vix":       base_vix,
        "portfolio_beta": round(portfolio_beta, 3),
        "scenarios":      scenarios,
        "worst_case":     worst_case,
    }
