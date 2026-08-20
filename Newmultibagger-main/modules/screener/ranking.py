"""
Ranking helpers: TickerShim, F-Score calculation wrappers.

Extracted from scripts/internal/screener.py.
"""

from dataclasses import dataclass, field
import pandas as pd

from modules.fundamentals import calculate_piotroski_f_score


@dataclass
class TickerShim:
    """
    Lightweight shim that wraps DataSourceManager output to look like a yfinance Ticker.
    Allows fundamentals.py functions to work without modification.
    """
    financials: pd.DataFrame = field(default_factory=pd.DataFrame)
    balance_sheet: pd.DataFrame = field(default_factory=pd.DataFrame)
    cashflow: pd.DataFrame = field(default_factory=pd.DataFrame)
    quarterly_financials: pd.DataFrame = field(default_factory=pd.DataFrame)


def _frame_from_attr(obj, *names):
    for name in names:
        frame = getattr(obj, name, pd.DataFrame())
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame
    return pd.DataFrame()


def _backfill_financial_statements(ticker, source_ticker):
    """Populate annual statement frames needed by the 9-point F-Score."""
    if ticker.financials.empty:
        ticker.financials = _frame_from_attr(source_ticker, "financials")
    if ticker.balance_sheet.empty:
        ticker.balance_sheet = _frame_from_attr(source_ticker, "balance_sheet")
    if ticker.cashflow.empty:
        ticker.cashflow = _frame_from_attr(source_ticker, "cashflow")


def _has_piotroski_statement_frames(ticker):
    return not ticker.financials.empty and not ticker.balance_sheet.empty


def _positive_int(value, default=0):
    try:
        v = int(value)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


def _calculate_f_score_with_method(ticker):
    """Calculate Piotroski F-Score, returning (score, max_possible, method)."""
    if _has_piotroski_statement_frames(ticker):
        try:
            score, max_possible = calculate_piotroski_f_score(ticker)
            return _positive_int(score), _positive_int(max_possible, 9), "piotroski_9pt"
        except Exception:
            pass
    return 0, 9, "unavailable"
