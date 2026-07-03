from __future__ import annotations

import importlib
from types import SimpleNamespace

import pandas as pd
import pytest


def _ticker_with_financials(years: list[str]):
    values = [100.0 * (1.1 ** i) for i in range(len(years))]
    shares = [10.0] * len(years)
    return SimpleNamespace(
        financials=pd.DataFrame(
            [values, values],
            index=["Total Revenue", "Net Income"],
            columns=years,
        ),
        balance_sheet=pd.DataFrame(
            [shares],
            index=["Ordinary Shares Number"],
            columns=years,
        ),
    )


@pytest.mark.parametrize("years", [["2021", "2022", "2023"], ["2020", "2021", "2022", "2023"], ["2019", "2020", "2021", "2022", "2023"]])
def test_yfinance_cagr_never_labels_short_history_as_5y(years):
    from modules.cagr_engine import calculate_all_cagrs

    result = calculate_all_cagrs(_ticker_with_financials(years))

    assert result["Revenue_CAGR_5Y"] is None
    assert result["PAT_CAGR_5Y"] is None
    assert result["EPS_CAGR_5Y"] is None


def test_yfinance_cagr_emits_5y_only_with_six_annual_points():
    from modules.cagr_engine import calculate_all_cagrs

    result = calculate_all_cagrs(
        _ticker_with_financials(["2018", "2019", "2020", "2021", "2022", "2023"])
    )

    assert result["Revenue_CAGR_5Y"] is not None
    assert result["PAT_CAGR_5Y"] is not None
    assert result["EPS_CAGR_5Y"] is not None


def test_normalized_cagr_never_labels_short_history_as_5y():
    from modules.cagr_engine import calculate_all_cagrs_from_normalized
    from modules.financial_adapter import NormalizedFinancials

    nf = NormalizedFinancials(
        revenue_series={"2019": 100, "2020": 120, "2021": 140, "2022": 160, "2023": 180},
        net_income_series={"2019": 10, "2020": 12, "2021": 14, "2022": 16, "2023": 18},
        shares_outstanding_series={"2019": 10, "2020": 10, "2021": 10, "2022": 10, "2023": 10},
        data_points=5,
    )

    result = calculate_all_cagrs_from_normalized(nf)

    assert result["Revenue_CAGR_5Y"] is None
    assert result["PAT_CAGR_5Y"] is None
    assert result["EPS_CAGR_5Y"] is None


def test_optimizer_cost_drag_matches_backtest_cost_model():
    from backtest.backtest_engine import compute_round_trip_cost
    from modules.portfolio.optimizer import PortfolioOptimizer

    gross_return = 0.20
    turnover = 2.0

    net = PortfolioOptimizer.net_returns_after_costs(
        gross_return,
        turnover,
        cap_category="Mid",
    )

    assert net == pytest.approx(gross_return - compute_round_trip_cost("Mid") * turnover)


def test_ticker_list_has_no_duplicates():
    import ticker_list

    assert len(ticker_list.TICKERS) == len(set(ticker_list.TICKERS))


def test_ticker_csv_paths_are_env_configurable(monkeypatch, tmp_path):
    import ticker_list

    csv_path = tmp_path / "nifty500.csv"
    monkeypatch.setenv("NIFTY_500_CSV_PATH", str(csv_path))

    reloaded = importlib.reload(ticker_list)
    try:
        assert reloaded.NIFTY_500_CSV_PATH == csv_path
    finally:
        monkeypatch.delenv("NIFTY_500_CSV_PATH", raising=False)
        importlib.reload(ticker_list)
