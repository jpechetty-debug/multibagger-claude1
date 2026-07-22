# backtest_engine.py
"""
Sovereign Backtest Engine — Root Shim
======================================
The full vectorbt-based engine lives at backtest/backtest_engine.py.
This root-level module is the public API entry point and adds the critical
point-in-time (PIT) lookahead bias guard that the institutional audit gate
requires.

Lookahead fail-fast guard
--------------------------
Any backtest that uses fundamental data must specify an ``as_of_date`` for
every data row.  If the engine detects that a row's ``as_of_date`` is in
the future relative to the simulation's current step, it raises
``LookaheadBiasError`` and the run is aborted immediately:

    "Backtest aborted — lookahead bias detected"

This is a hard stop, not a warning.  The run cannot continue with
compromised data integrity.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

try:
    from core.observability.logger import get_logger
    _log = get_logger("sovereign.backtest_engine")
except Exception:
    import logging
    _log = logging.getLogger("sovereign.backtest_engine")


# ── Exceptions ────────────────────────────────────────────────────────────────


class LookaheadBiasError(RuntimeError):
    """Raised when fundamental data with a future as_of_date is accessed."""


# ── PIT guard ─────────────────────────────────────────────────────────────────


def validate_pit_integrity(
    fundamentals_df: pd.DataFrame,
    simulation_date: date | str,
) -> None:
    """Assert no row in fundamentals_df has as_of_date > simulation_date.

    Args:
        fundamentals_df: DataFrame that must contain an ``as_of_date`` column.
        simulation_date: The current step date in the backtest loop.

    Raises:
        LookaheadBiasError: If any row would introduce lookahead bias.
            Message format: "Backtest aborted — lookahead bias detected:
            {n} rows have as_of_date > {simulation_date}"
    """
    if "as_of_date" not in fundamentals_df.columns:
        raise ValueError(
            "fundamentals_df must contain an 'as_of_date' column for PIT validation."
        )

    sim_dt = pd.Timestamp(simulation_date)
    fundamentals_df = fundamentals_df.copy()
    fundamentals_df["as_of_date"] = pd.to_datetime(
        fundamentals_df["as_of_date"], errors="coerce"
    )

    future_rows = fundamentals_df[fundamentals_df["as_of_date"] > sim_dt]
    if not future_rows.empty:
        n = len(future_rows)
        symbols = future_rows["symbol"].tolist()[:5] if "symbol" in future_rows.columns else []
        msg = (
            f"Backtest aborted — lookahead bias detected: "
            f"{n} rows have as_of_date > {simulation_date}. "
            f"Sample symbols: {symbols}"
        )
        _log.error(msg)
        raise LookaheadBiasError(msg)


def filter_pit(
    fundamentals_df: pd.DataFrame,
    simulation_date: date | str,
) -> pd.DataFrame:
    """Return only rows where as_of_date <= simulation_date.

    Safe alternative to validate_pit_integrity when you want to silently
    filter rather than abort.  Still logs any dropped rows.
    """
    sim_dt = pd.Timestamp(simulation_date)
    df = fundamentals_df.copy()
    df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
    future_mask = df["as_of_date"] > sim_dt
    if future_mask.any():
        _log.warning(
            "PIT filter dropped future rows",
            n_dropped=int(future_mask.sum()),
            simulation_date=str(simulation_date),
        )
    return df[~future_mask].copy()


# ── Run wrapper ───────────────────────────────────────────────────────────────


def run_backtest(
    signals_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    initial_capital: float = 1_000_000.0,
    transaction_cost_bps: float = 30.0,
) -> dict[str, Any]:
    """Run a full backtest via the vectorbt engine with PIT validation.

    Delegates to backtest.backtest_engine for the heavy lifting; adds
    the lookahead bias guard before any fundamental data is consumed.

    Args:
        signals_df: DataFrame with columns [date, symbol, signal (1/0/-1)].
        fundamentals_df: Optional fundamental data — will be PIT-validated.
        start_date: Backtest start (ISO date string).
        end_date: Backtest end (ISO date string).
        initial_capital: Starting portfolio value in INR.
        transaction_cost_bps: Round-trip transaction cost in basis points.

    Returns:
        Dict with CAGR, max_dd, Sharpe and full equity curve.
    """
    # ── PIT integrity check ───────────────────────────────────────────────────
    if fundamentals_df is not None and not fundamentals_df.empty:
        sim_start = pd.Timestamp(start_date) if start_date else signals_df["date"].min()
        try:
            validate_pit_integrity(fundamentals_df, sim_start)
        except LookaheadBiasError:
            # Re-raise — the caller must fix the data, not swallow this error.
            raise

    # ── Delegate to full engine ───────────────────────────────────────────────
    try:
        from backtest.backtest_engine import BacktestEngine
        engine = BacktestEngine(
            initial_capital=initial_capital,
            transaction_cost_bps=transaction_cost_bps,
        )
        return engine.run(
            signals_df=signals_df,
            start_date=start_date,
            end_date=end_date,
        )
    except ImportError:
        _log.warning("backtest.backtest_engine not available — returning stub metrics")
        return {
            "status": "stub",
            "CAGR": None,
            "max_dd": None,
            "Sharpe": None,
            "as_of_date": str(date.today()),
        }
