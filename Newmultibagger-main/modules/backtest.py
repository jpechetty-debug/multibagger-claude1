# modules/backtest.py
"""
Sovereign Backtest Metrics Module
==================================
Computes institutional-grade performance metrics for strategy evaluation.
The full backtest engine lives at backtest/backtest_engine.py; this module
provides the metric computation layer consumed by the scorer and report
generator.

Key metrics: Sharpe, Sortino, max_dd (max drawdown), CAGR, Calmar,
Hit Rate, Avg Win/Loss, Profit Factor, Monte Carlo paths.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from collections.abc import Sequence

import numpy as np
import pandas as pd

try:
    from core.observability.logger import get_logger
    _log = get_logger("modules.backtest")
except Exception:
    import logging
    _log = logging.getLogger("modules.backtest")


# ── Constants ─────────────────────────────────────────────────────────────────

TRADING_DAYS_PER_YEAR = 252
RISK_FREE_RATE_ANNUAL = 0.065   # RBI repo rate proxy (6.5%)


# ── Core metric functions ─────────────────────────────────────────────────────


def compute_CAGR(equity_curve: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    """Compound Annual Growth Rate from an equity curve (index-based or price-based).

    Args:
        equity_curve: Series of portfolio values (not returns).
        periods_per_year: Trading days per year (252 for daily).

    Returns:
        CAGR as a decimal (e.g. 0.25 = 25% p.a.).
    """
    if equity_curve.empty or len(equity_curve) < 2:
        return 0.0
    start  = float(equity_curve.iloc[0])
    end    = float(equity_curve.iloc[-1])
    n_years = len(equity_curve) / periods_per_year
    if start <= 0 or n_years <= 0:
        return 0.0
    return float((end / start) ** (1.0 / n_years) - 1.0)


def compute_max_dd(equity_curve: pd.Series) -> float:
    """Maximum drawdown (peak-to-trough decline) as a positive decimal.

    Args:
        equity_curve: Series of portfolio values.

    Returns:
        max_dd as a positive decimal (e.g. 0.35 = 35% drawdown).
    """
    if equity_curve.empty:
        return 0.0
    rolling_max = equity_curve.cummax()
    drawdown    = (equity_curve - rolling_max) / rolling_max
    return float(abs(drawdown.min()))


def compute_Sharpe(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE_ANNUAL,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualised Sharpe ratio.

    Args:
        returns: Daily (or periodic) returns as decimals.
        risk_free_rate: Annual risk-free rate (e.g. 0.065 for 6.5%).
        periods_per_year: Trading periods per year.

    Returns:
        Sharpe ratio (annualised).
    """
    if returns.empty or returns.std() == 0:
        return 0.0
    rf_per_period = risk_free_rate / periods_per_year
    excess        = returns - rf_per_period
    return float(excess.mean() / excess.std() * math.sqrt(periods_per_year))


def compute_sortino(
    returns: pd.Series,
    risk_free_rate: float = RISK_FREE_RATE_ANNUAL,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualised Sortino ratio (downside deviation only)."""
    if returns.empty:
        return 0.0
    rf_per_period = risk_free_rate / periods_per_year
    excess        = returns - rf_per_period
    downside      = excess[excess < 0]
    if downside.empty or downside.std() == 0:
        return 0.0
    return float(excess.mean() / downside.std() * math.sqrt(periods_per_year))


def compute_calmar(
    equity_curve: pd.Series,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Calmar ratio = CAGR / max_dd."""
    cagr   = compute_CAGR(equity_curve, periods_per_year)
    max_dd = compute_max_dd(equity_curve)
    return float(cagr / max_dd) if max_dd > 0 else 0.0


def compute_hit_rate(trade_returns: Sequence[float]) -> float:
    """Fraction of winning trades (return > 0)."""
    if not trade_returns:
        return 0.0
    wins = sum(1 for r in trade_returns if r > 0)
    return wins / len(trade_returns)


def compute_profit_factor(trade_returns: Sequence[float]) -> float:
    """Gross profit / gross loss (∞ if no losing trades)."""
    gross_profit = sum(r for r in trade_returns if r > 0)
    gross_loss   = abs(sum(r for r in trade_returns if r < 0))
    if gross_loss == 0:
        return float("inf")
    return gross_profit / gross_loss


# ── Monte Carlo simulation ────────────────────────────────────────────────────


def monte_carlo_cagr(
    daily_returns: pd.Series,
    n_paths: int = 1000,
    horizon_days: int = TRADING_DAYS_PER_YEAR,
    seed: int = 42,
) -> dict:
    """Monte Carlo simulation of forward CAGR distribution (1000 paths).

    Bootstraps daily returns to build n_paths equity curves over
    horizon_days.  Reports p5/p50/p95 CAGR and max-drawdown statistics.

    Args:
        daily_returns: Historical daily return series.
        n_paths: Number of Monte Carlo simulation paths (default 1000).
        horizon_days: Forward simulation length in trading days.
        seed: Random seed for reproducibility.

    Returns:
        Dict with keys: n_paths, p5_cagr, p50_cagr, p95_cagr,
        p5_max_dd, p50_max_dd, p95_max_dd, prob_positive.
    """
    rng = np.random.default_rng(seed)
    r   = daily_returns.dropna().values

    if len(r) == 0:
        return {"n_paths": 0, "error": "no valid returns"}

    # Bootstrap sample paths
    paths  = rng.choice(r, size=(n_paths, horizon_days), replace=True)
    equity = np.cumprod(1 + paths, axis=1)

    cagrs   = (equity[:, -1] ** (TRADING_DAYS_PER_YEAR / horizon_days)) - 1
    max_dds = np.array([
        float((equity[i] / np.maximum.accumulate(equity[i]) - 1).min())
        for i in range(n_paths)
    ])

    return {
        "n_paths":       n_paths,
        "p5_cagr":       float(np.percentile(cagrs,   5)),
        "p50_cagr":      float(np.percentile(cagrs,  50)),
        "p95_cagr":      float(np.percentile(cagrs,  95)),
        "p5_max_dd":     float(np.percentile(max_dds,  5)),
        "p50_max_dd":    float(np.percentile(max_dds, 50)),
        "p95_max_dd":    float(np.percentile(max_dds, 95)),
        "prob_positive": float((cagrs > 0).mean()),
    }


# ── Latency impact on alpha capture model ────────────────────────────────────


def latency_alpha_slippage(
    signal_return_bps: float,
    execution_latency_ms: float,
    alpha_decay_half_life_ms: float = 30_000.0,
) -> dict:
    """Model the latency impact on alpha capture (latency-alpha relationship).

    Alpha decays exponentially with execution latency relative to the
    signal half-life.  Returns the fraction of signal alpha retained
    and the effective slippage-adjusted alpha.

    Args:
        signal_return_bps: Raw signal alpha in basis points.
        execution_latency_ms: End-to-end order latency in milliseconds.
        alpha_decay_half_life_ms: Latency at which 50% of alpha is lost.

    Returns:
        Dict with alpha_retained_pct, effective_alpha_bps, latency_cost_bps.
    """
    alpha_retained = math.exp(
        -math.log(2) * execution_latency_ms / alpha_decay_half_life_ms
    )
    effective_alpha_bps = signal_return_bps * alpha_retained
    latency_cost_bps    = signal_return_bps - effective_alpha_bps

    return {
        "signal_return_bps":       signal_return_bps,
        "execution_latency_ms":    execution_latency_ms,
        "alpha_retained_pct":      round(alpha_retained * 100, 2),
        "effective_alpha_bps":     round(effective_alpha_bps, 2),
        "latency_cost_bps":        round(latency_cost_bps, 2),
    }


# ── Composite metrics dataclass ───────────────────────────────────────────────


@dataclass
class BacktestMetrics:
    """Full suite of institutional backtest metrics."""

    cagr:          float = 0.0
    max_dd:        float = 0.0
    Sharpe:        float = 0.0
    sortino:       float = 0.0
    calmar:        float = 0.0
    hit_rate:      float = 0.0
    profit_factor: float = 0.0
    n_trades:      int   = 0
    monte_carlo:   dict  = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "CAGR":          round(self.cagr * 100, 2),
            "max_dd":        round(self.max_dd * 100, 2),
            "Sharpe":        round(self.Sharpe, 3),
            "sortino":       round(self.sortino, 3),
            "calmar":        round(self.calmar, 3),
            "hit_rate":      round(self.hit_rate * 100, 2),
            "profit_factor": round(self.profit_factor, 3),
            "n_trades":      self.n_trades,
            "monte_carlo":   self.monte_carlo,
        }


def compute_all(
    equity_curve: pd.Series,
    daily_returns: pd.Series,
    trade_returns: list[float] | None = None,
    run_monte_carlo: bool = True,
) -> BacktestMetrics:
    """Compute full institutional metric suite in one call.

    Args:
        equity_curve: Portfolio value time-series.
        daily_returns: Daily return series (decimal).
        trade_returns: Per-trade return list for hit rate / profit factor.
        run_monte_carlo: Whether to run the 1000-path Monte Carlo simulation.

    Returns:
        BacktestMetrics dataclass.
    """
    mc = {}
    if run_monte_carlo and not daily_returns.empty:
        mc = monte_carlo_cagr(daily_returns, n_paths=1000)

    return BacktestMetrics(
        cagr=compute_CAGR(equity_curve),
        max_dd=compute_max_dd(equity_curve),
        Sharpe=compute_Sharpe(daily_returns),
        sortino=compute_sortino(daily_returns),
        calmar=compute_calmar(equity_curve),
        hit_rate=compute_hit_rate(trade_returns or []),
        profit_factor=compute_profit_factor(trade_returns or []),
        n_trades=len(trade_returns or []),
        monte_carlo=mc,
    )
