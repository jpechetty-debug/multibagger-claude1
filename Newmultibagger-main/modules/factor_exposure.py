"""
Factor Exposure Monitoring
--------------------------
OLS regression of portfolio returns against market factors.
Alerts on concentrated factor bets (momentum > 0.5, size < -0.3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_factor_betas(
    portfolio_returns: pd.Series,
    factor_returns: dict[str, pd.Series],
) -> dict[str, dict]:
    """Regress portfolio returns against each factor via OLS.

    Args:
        portfolio_returns: Period return series.
        factor_returns: ``{factor_name: return_series}`` aligned to same index.

    Returns:
        ``{factor_name: {"beta": float, "t_stat": float, "r2": float}}``.
    """
    results: dict[str, dict] = {}
    for name, factor in factor_returns.items():
        aligned = pd.DataFrame({"port": portfolio_returns, "factor": factor}).dropna()
        if len(aligned) < 3:
            results[name] = {"beta": 0.0, "t_stat": 0.0, "r2": 0.0}
            continue

        x = aligned["factor"].values
        y = aligned["port"].values
        x_mean = x.mean()
        y_mean = y.mean()
        ss_xx = float(np.sum((x - x_mean) ** 2))
        if ss_xx == 0:
            results[name] = {"beta": 0.0, "t_stat": 0.0, "r2": 0.0}
            continue

        beta = float(np.sum((x - x_mean) * (y - y_mean)) / ss_xx)
        alpha = y_mean - beta * x_mean
        residuals = y - (alpha + beta * x)
        n = len(aligned)
        se_beta = float(np.sqrt(np.sum(residuals ** 2) / (n - 2) / ss_xx)) if n > 2 else 0.0
        t_stat = beta / se_beta if se_beta > 0 else 0.0

        ss_tot = float(np.sum((y - y_mean) ** 2))
        ss_res = float(np.sum(residuals ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        results[name] = {
            "beta": round(beta, 4),
            "t_stat": round(t_stat, 4),
            "r2": round(r2, 4),
        }
    return results


def check_factor_alerts(
    betas: dict[str, dict],
    momentum_threshold: float = 0.5,
    size_threshold: float = -0.3,
) -> list[str]:
    """Return alert strings for concentrated factor bets."""
    alerts: list[str] = []
    for name, vals in betas.items():
        b = vals.get("beta", 0.0)
        if "momentum" in name.lower() and b > momentum_threshold:
            alerts.append(f"MOMENTUM_OVERLOAD: {name} beta={b:.3f} > {momentum_threshold}")
        if "size" in name.lower() and b < size_threshold:
            alerts.append(f"SIZE_TILT: {name} beta={b:.3f} < {size_threshold}")
    return alerts


async def fetch_factor_returns_with_retry(symbol: str, period: str = "1y") -> dict:
    """Fetch price history for factor computation with exponential backoff.

    Wraps the yfinance fetch in the project-standard retry harness so
    transient 429 / connection errors are handled uniformly.
    """
    import yfinance as yf

    from modules.retry_utils import run_with_exponential_backoff

    async def _fetch():
        ticker = yf.Ticker(symbol)
        hist   = ticker.history(period=period)
        if hist.empty:
            return {"symbol": symbol, "error": "no data"}
        return {
            "symbol":  symbol,
            "returns": hist["Close"].pct_change().dropna().tolist(),
            "dates":   hist.index.strftime("%Y-%m-%d").tolist(),
        }

    return await run_with_exponential_backoff(
        _fetch,
        context=f"factor_returns:{symbol}",
        should_retry=lambda exc: "429" in str(exc) or "ConnectionError" in str(exc),
    )
