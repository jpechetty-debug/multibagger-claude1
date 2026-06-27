from types import SimpleNamespace

import pandas as pd

from scripts.internal import screener


def test_yfinance_backfill_populates_statement_frames_from_cash_flow_alias():
    ticker = screener.TickerShim()
    source = SimpleNamespace(
        financials=pd.DataFrame({"2024": [100]}, index=["Net Income"]),
        balance_sheet=pd.DataFrame({"2024": [1000]}, index=["Total Assets"]),
        cash_flow=pd.DataFrame({"2024": [120]}, index=["Operating Cash Flow"]),
    )

    screener._backfill_financial_statements(ticker, source)

    assert not ticker.financials.empty
    assert not ticker.balance_sheet.empty
    assert not ticker.cashflow.empty


def test_f_score_uses_screener_score_with_explicit_7_point_max():
    ticker = screener.TickerShim()

    f_score, method, max_score = screener._calculate_f_score_with_method(
        ticker,
        {"source": "screener_in", "F_Score": 5},
        {},
        debt_equity=0.2,
    )

    assert (f_score, method, max_score) == (5, "screener_in", 7)


def test_f_score_uses_5_point_inline_when_structural_sources_missing():
    ticker = screener.TickerShim()
    info = {
        "returnOnAssets": 0.08,
        "operatingCashflow": 200,
        "netIncomeToCommon": 100,
        "grossMargins": 0.3,
    }

    f_score, method, max_score = screener._calculate_f_score_with_method(
        ticker,
        {},
        info,
        debt_equity=0.2,
    )

    assert (f_score, method, max_score) == (5, "5pt_inline", 5)


def test_f_score_prefers_9_point_when_statements_are_available(monkeypatch):
    ticker = screener.TickerShim(
        financials=pd.DataFrame({"2024": [100]}, index=["Net Income"]),
        balance_sheet=pd.DataFrame({"2024": [1000]}, index=["Total Assets"]),
        cashflow=pd.DataFrame({"2024": [120]}, index=["Operating Cash Flow"]),
    )
    monkeypatch.setattr(screener, "calculate_piotroski_f_score", lambda _: 8)

    f_score, method, max_score = screener._calculate_f_score_with_method(
        ticker,
        {"source": "screener_in", "F_Score": 5},
        {},
        debt_equity=0.2,
    )

    assert (f_score, method, max_score) == (8, "9pt_piotroski", 9)
