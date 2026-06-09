"""
/api/factor-exposure  — India Factor Exposure endpoint
-------------------------------------------------------
Regresses a portfolio's trade-level returns against the six India equity
factors (market, size, value, momentum, quality, low_vol) using the OLS
engine in ``modules/factor_exposure.py``.

Routes
~~~~~~
GET  /api/factor-exposure
     Analyse the full closed-trade history held in ``portfolio_history.db``.
     Returns per-factor beta, t-stat, R², plus any concentration alerts.

GET  /api/factor-exposure/meta
     Lightweight health-check: factor CSV availability & date range.

Query parameters (GET /api/factor-exposure)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
start   ISO date, e.g. 2023-01-01   – restrict factor window (optional)
end     ISO date, e.g. 2024-12-31   – restrict factor window (optional)
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from modules.connections import _run_blocking
from modules.factor_exposure import check_factor_alerts, compute_factor_betas
from modules.india_factor_loader import factor_metadata, load_factor_returns
from core.observability.logger import get_logger

_log = get_logger("api.factor_exposure")

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_portfolio_returns() -> pd.Series:
    """
    Derive a weekly portfolio return series from closed trades in
    ``portfolio_history.db``.

    Strategy
    --------
    1. Load all CLOSED trades with ``exit_date`` and ``pnl_pct``.
    2. Parse ``exit_date`` → DatetimeIndex, resample to weekly (Monday freq)
       by averaging ``pnl_pct / 100`` across trades that closed that week.
    3. If no closed trades exist fall back to a zero-length Series so the
       caller receives a graceful empty result rather than an exception.
    """
    try:
        from modules.tracking.tracker import PortfolioTracker

        tracker = PortfolioTracker()
        history_df: pd.DataFrame = tracker.get_trade_history()
    except Exception as exc:  # DB not initialised yet, etc.
        _log.warning("Could not load trade history", error=str(exc))
        return pd.Series(dtype=float, name="portfolio")

    if history_df.empty:
        return pd.Series(dtype=float, name="portfolio")

    # pnl_pct is stored as a percentage (e.g. 4.5 means 4.5 %)
    history_df["pnl_decimal"] = pd.to_numeric(history_df["pnl_pct"], errors="coerce") / 100.0
    history_df["exit_dt"] = pd.to_datetime(history_df["exit_date"], errors="coerce")
    history_df = history_df.dropna(subset=["exit_dt", "pnl_decimal"])

    if history_df.empty:
        return pd.Series(dtype=float, name="portfolio")

    series = (
        history_df
        .set_index("exit_dt")["pnl_decimal"]
        .resample("W-MON")
        .mean()
        .rename("portfolio")
    )
    return series


def _run_factor_analysis(
    start: str | None,
    end: str | None,
) -> dict[str, Any]:
    """Core computation — runs in a thread via ``_run_blocking``."""
    portfolio_returns = _build_portfolio_returns()

    if portfolio_returns.empty:
        return {
            "status": "no_data",
            "message": "No closed trades found. Execute and close trades to populate factor exposure.",
            "betas": {},
            "alerts": [],
            "factor_window": {"start": start, "end": end},
            "portfolio_weeks": 0,
            "timestamp": datetime.utcnow().isoformat(),
        }

    factor_returns = load_factor_returns(start=start, end=end)
    if not factor_returns:
        meta = factor_metadata()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "India factor returns data unavailable.",
                "hint": "Ensure data/india_factor_returns.csv exists.",
                "meta": meta,
            },
        )

    # Align portfolio returns to the factor window
    factor_idx = next(iter(factor_returns.values())).index
    port_aligned = portfolio_returns.reindex(factor_idx)

    if port_aligned.dropna().empty:
        # Portfolio dates don't overlap with the factor window
        port_range = (
            f"{portfolio_returns.index.min().date()} – {portfolio_returns.index.max().date()}"
        )
        factor_range = f"{factor_idx.min().date()} – {factor_idx.max().date()}"
        return {
            "status": "no_overlap",
            "message": (
                f"Portfolio trade dates ({port_range}) do not overlap with "
                f"the factor window ({factor_range}). Adjust start/end or trade more."
            ),
            "betas": {},
            "alerts": [],
            "factor_window": {"start": str(factor_idx.min().date()), "end": str(factor_idx.max().date())},
            "portfolio_weeks": int(portfolio_returns.notna().sum()),
            "timestamp": datetime.utcnow().isoformat(),
        }

    betas = compute_factor_betas(port_aligned, factor_returns)
    alerts = check_factor_alerts(betas)

    meta = factor_metadata()
    return {
        "status": "ok",
        "betas": betas,
        "alerts": alerts,
        "factor_window": {
            "start": str(factor_idx.min().date()),
            "end": str(factor_idx.max().date()),
        },
        "portfolio_weeks": int(port_aligned.dropna().shape[0]),
        "data_source": str(meta.get("rows", 0)) + " weekly factor observations",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/api/factor-exposure/meta")
async def get_factor_meta():
    """Return India factor CSV availability and date coverage."""
    try:
        meta = await _run_blocking(factor_metadata)
        return meta
    except Exception as exc:
        _log.error("factor_meta failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/api/factor-exposure")
async def get_factor_exposure(
    start: str | None = Query(None, description="Restrict factor window start (YYYY-MM-DD)"),
    end: str | None = Query(None, description="Restrict factor window end (YYYY-MM-DD)"),
):
    """
    Regress the portfolio's closed-trade weekly returns against six
    India equity factors and surface any concentration alerts.

    **Response fields**

    - ``betas``: ``{factor: {beta, t_stat, r2}}`` — OLS coefficients.
    - ``alerts``: List of human-readable alert strings (e.g. MOMENTUM_OVERLOAD).
    - ``factor_window``: Actual start/end of the factor data used.
    - ``portfolio_weeks``: Number of matched weekly observations.
    - ``status``: ``"ok"`` | ``"no_data"`` | ``"no_overlap"``.
    """
    try:
        # Validate date params early for a clean 400 rather than a 500
        for label, val in [("start", start), ("end", end)]:
            if val is not None:
                try:
                    date.fromisoformat(val)
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid {label} date '{val}'. Use YYYY-MM-DD.",
                    )

        result = await _run_blocking(_run_factor_analysis, start, end)
        return result

    except HTTPException:
        raise
    except Exception as exc:
        _log.error("factor_exposure failed", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
