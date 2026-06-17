import os

import numpy as np
import pandas as pd
import yfinance as yf

from modules.recovery import calculate_recovery_metrics
from modules.risk.slippage import calculate_slippage
from modules.tax_efficiency import calculate_tax_efficiency
from core.observability.logger import get_logger
_log = get_logger("modules.backtest_engine_v2")

RF_ANNUAL = float(os.getenv("RISK_FREE_RATE_ANNUAL", "0.065"))
# Number of trailing trading days used to estimate each ticker's average daily value.
_SLIPPAGE_LOOKBACK_DAYS = 10


def _compute_portfolio_slippage(
    valid_tickers: list[str],
    ohlcv: pd.DataFrame,
    weights: dict[str, float] | None,
    w_sum: float,
) -> tuple[float, dict[str, tuple[float, str]]]:
    """Compute a portfolio-weighted average one-way slippage using slippage.py tiers.

    Uses the last ``_SLIPPAGE_LOOKBACK_DAYS`` rows of the downloaded OHLCV data
    to estimate each ticker's average daily traded value in Crores, then calls
    ``calculate_slippage()`` for the liquidity-tier classification.

    Returns:
        weighted_avg_slippage: Portfolio-level one-way slippage % (float).
        per_ticker:            {symbol: (slippage_pct, tier_reason)} for the report.
    """
    per_ticker: dict[str, tuple[float, str]] = {}
    total_slip = 0.0
    total_w = 0.0

    for sym in valid_tickers:
        try:
            # Extract Close and Volume for this ticker from the MultiIndex DataFrame.
            close_col = ohlcv["Close"][sym] if ("Close", sym) in ohlcv.columns else ohlcv[sym]
            vol_col   = ohlcv["Volume"][sym] if ("Volume", sym) in ohlcv.columns else None

            if vol_col is None or vol_col.empty:
                # Volume unavailable — fall back to mid-tier assumption.
                slip_pct, reason = 0.6, "Mid Cap (no volume)"
            else:
                lookback = min(_SLIPPAGE_LOOKBACK_DAYS, len(close_col))
                avg_price  = close_col.tail(lookback).mean()
                avg_vol_sh = vol_col.tail(lookback).mean()          # shares
                # Convert to Rs Crore: shares × price / 1_00_00_000
                avg_vol_cr = (avg_vol_sh * avg_price) / 1_00_00_000
                # market_cap_cr is accepted by calculate_slippage but not used in
                # any tier branch — pass 0 safely (see slippage.py).
                slip_pct, reason = calculate_slippage(0, avg_vol_cr)

        except Exception:
            slip_pct, reason = 1.0, "Unknown (data error)"

        per_ticker[sym] = (slip_pct, reason)

        # Portfolio weight for this ticker
        if weights and w_sum > 0:
            w = weights.get(sym, 0) / w_sum
        else:
            w = 1.0 / len(valid_tickers)   # equal weight

        total_slip += slip_pct * w
        total_w    += w

    weighted_avg = total_slip / total_w if total_w > 0 else 1.0
    return weighted_avg, per_ticker


def run_performance_analysis(
    tickers,
    weights=None,
    benchmark_symbol="^NSEI",
    period="1y",
    start_date=None,
    end_date=None,
    strategy_type="Balanced (Neutral)",
):
    """Phase 16/17/31: Backtest Engine with Walk-Forward Capability.

    Args:
        tickers:          List of NSE symbols.
        weights:          Dict {symbol: weight} for score-based sizing.
        benchmark_symbol: Yahoo Finance ticker for benchmark (default ^NSEI).
        period:           "1y", "2y" etc — used when dates are not provided.
        start_date:       "YYYY-MM-DD" — overrides period when both dates given.
        end_date:         "YYYY-MM-DD" — overrides period when both dates given.
        strategy_type:    Passed to calculate_tax_efficiency() so the correct
                          turnover assumption is used.  Valid values:
                          "Momentum", "Quality", "Value", "Balanced (Neutral)",
                          "Aggressive (Bull)", "Defensive (Bear)".
    """
    if weights:
        _log.info("\nrunning Phase 17/31: Weighted Portfolio Backtest...")
    else:
        _log.info("\nrunning Phase 16/31: Equal-Weight Backtest...")

    if not tickers:
        _log.info("No tickers to backtest.")
        return

    try:
        # --- 1. Download full OHLCV (Close + Volume needed for slippage) ---
        all_symbols = tickers + [benchmark_symbol]

        if start_date and end_date:
            _log.info(f"  📅 Range: {start_date} to {end_date}")
            ohlcv = yf.download(all_symbols, start=start_date, end=end_date, progress=False)
        else:
            _log.info(f"  📅 Period: {period}")
            ohlcv = yf.download(all_symbols, period=period, progress=False)

        if ohlcv.empty:
            _log.error("Failed to download backtest data.")
            return

        # Subset to Close prices for all return calculations.
        data = ohlcv["Close"] if "Close" in ohlcv.columns else ohlcv

        # --- 2. Returns ---
        returns = data.pct_change().dropna()

        valid_tickers = [t for t in tickers if t in data.columns]
        if not valid_tickers:
            _log.info("No valid data for selected tickers.")
            return

        # Normalised weight sum (used by both return calc and slippage weighting).
        w_sum = sum(weights.get(t, 0) for t in valid_tickers) if weights else 0

        if weights and w_sum > 0:
            weighted_rets = pd.DataFrame()
            for t in valid_tickers:
                w = weights.get(t, 0) / w_sum
                weighted_rets[t] = returns[t] * w
            strategy_returns = weighted_rets.sum(axis=1)
            _log.info("Applied Smart Sizing (Score-Based Weights).")
        else:
            strategy_returns = returns[valid_tickers].mean(axis=1)

        # --- 3. Benchmark ---
        if benchmark_symbol in returns.columns:
            benchmark_returns = returns[benchmark_symbol]
        else:
            benchmark_returns = pd.Series(0, index=returns.index)

        # --- 4. Cumulative Returns ---
        cum_strategy  = (1 + strategy_returns).cumprod()
        cum_benchmark = (1 + benchmark_returns).cumprod()

        # --- 5. Core Metrics ---
        total_return_strat = (cum_strategy.iloc[-1]  - 1) * 100
        total_return_bench = (cum_benchmark.iloc[-1] - 1) * 100

        days  = len(data)
        years = days / 252.0
        cagr_strategy  = ((cum_strategy.iloc[-1])  ** (1 / years) - 1) * 100
        cagr_benchmark = ((cum_benchmark.iloc[-1]) ** (1 / years) - 1) * 100

        rolling_max = cum_strategy.cummax()
        drawdown    = cum_strategy / rolling_max - 1
        max_dd      = drawdown.min() * 100

        rf_daily       = RF_ANNUAL / 252
        excess_returns = strategy_returns - rf_daily
        sharpe = (
            (excess_returns.mean() / excess_returns.std()) * np.sqrt(252)
            if excess_returns.std() > 0 else 0.0
        )

        alpha = cagr_strategy - cagr_benchmark

        # --- 6. Phase 33: Liquidity-tiered slippage (replaces hardcoded 1.0%) ---
        # Calculate per-ticker average daily traded value from the downloaded Volume
        # data, classify each ticker into a slippage tier via slippage.py, then
        # take the portfolio-weighted average as the one-way cost.
        slippage_one_way, per_ticker_slip = _compute_portfolio_slippage(
            valid_tickers, ohlcv, weights, w_sum
        )
        round_trip_drag = slippage_one_way * 2
        net_cagr  = cagr_strategy - round_trip_drag
        net_alpha = net_cagr - cagr_benchmark

        # --- 7. Phase 37: Recovery Metrics ---
        rec_days, avg_rec, ulcer = calculate_recovery_metrics(cum_strategy)

        # --- 8. Phase 38: Tax Efficiency (strategy-aware) ---
        # strategy_type is now a proper parameter so callers can pass the correct
        # turnover assumption instead of defaulting to "Balanced (Neutral)" every
        # time.  A Momentum strategy has ~2.5× turnover vs ~0.8× for Balanced,
        # which changes the effective tax rate by ~3 percentage points.
        post_tax_cagr, tax_drag, turnover, eff_tax = calculate_tax_efficiency(
            net_cagr, strategy_type=strategy_type
        )

        # --- 9. Report ---
        _log.info("\n" + "=" * 40)
        _log.info("📊 PHASE 16/33/37/38: BACKTEST REPORT")
        _log.info("=" * 40)
        _log.info(f"Strategy: {len(valid_tickers)} Stocks  |  Type: {strategy_type}")
        _log.info(f"Benchmark: {benchmark_symbol}")
        _log.info("-" * 55)
        _log.info(f"{'Metric':<15} | {'Gross':<8} | {'Net':<8} | {'Post-Tax':<8}")
        _log.info("-" * 55)
        _log.info(f"{'Total Return':<15} | {total_return_strat:>7.1f}% | {'--':>7}  | {'--':>7}")
        _log.info(f"{'CAGR':<15} | {cagr_strategy:>7.1f}% | {net_cagr:>7.1f}% | {post_tax_cagr:>7.1f}%")
        _log.info(f"{'Benchmark CAGR':<15} | {cagr_benchmark:>7.1f}% | {'--':>7}  | {'--':>7}")
        _log.info(f"{'Drawdown':<15} | {max_dd:>7.1f}% | {max_dd:>7.1f}% | {max_dd:>7.1f}%")
        _log.info(f"{'Sharpe':<15} | {sharpe:>7.2f}  | {sharpe:>7.2f}  | {'--':>7}")
        _log.info("-" * 55)
        _log.info(
            f"Slippage (1W)  : {slippage_one_way:.2f}%  "
            f"(RT drag {round_trip_drag:.2f}%)  |  Turnover: {turnover:.1f}×/yr  "
            f"Tax: {eff_tax:.1f}%"
        )
        _log.info(f"Recovery Days  : {rec_days:>4}d avg {avg_rec:.0f}d  |  Ulcer Idx: {ulcer:.2f}")
        _log.info("-" * 55)
        _log.info("Slippage breakdown:")
        for sym, (slip, reason) in per_ticker_slip.items():
            _log.info(f"  {sym:<18} {slip:.2f}%  ({reason})")
        _log.info("-" * 55)

        if alpha > 0:
            _log.info(f"✅ GROSS ALPHA: +{alpha:.1f}%")
        else:
            _log.warning(f"❌ GROSS ALPHA: {alpha:.1f}%")

        if post_tax_cagr > cagr_benchmark:
            _log.info(f"🏆 REAL ALPHA : +{post_tax_cagr - cagr_benchmark:.1f}% (Post-Tax)")
        else:
            _log.info("💸 TAX TRAP   : Strategy loses edge after Tax/Slippage")

        _log.info("=" * 40 + "\n")

        return {
            "CAGR": cagr_strategy,
            "TotalReturn": total_return_strat,
            "BenchmarkCAGR": cagr_benchmark,
            "BenchmarkTotalReturn": total_return_bench,
            "NetCAGR": net_cagr,
            "PostTaxCAGR": post_tax_cagr,
            "MaxDD": max_dd,
            "Sharpe": sharpe,
            "Alpha": alpha,
            "NetAlpha": net_alpha,
            "SlippageOneway": slippage_one_way,
            "RoundTripDrag": round_trip_drag,
        }

    except Exception as e:
        _log.error(f"Backtest Error: {e}")
