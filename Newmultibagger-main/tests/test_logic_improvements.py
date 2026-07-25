from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from modules.adapters.nse_xbrl_provider import NSEXBRLProvider
from modules.cagr_engine import _cagr_from_series, _compute_multi_period_cagr, _turnaround_growth
from modules.pit_auditor import _get_lag_for_metric
from modules.risk.correlation import calculate_portfolio_correlation
from scripts.internal.liquidity_simulator import _fetch_recent_volume_and_price


class LocalFilingMock:
    def __init__(self, period_end: date, bs_equity: float, q_pat: float):
        self.period_end = period_end
        self.bs_equity = bs_equity
        self.q_pat = q_pat
        self.is_consolidated = True
        self.q_revenue = 100.0
        self.q_diluted_eps = 2.0
        self.debt_equity_ratio = 0.5
        self.book_value_per_share = 50.0
        self.is_audited = True
        self.seq_id = "SEQ1"


def test_correlation_returns_based():
    # Mock database read and yfinance download with trending prices that would have high price correlation
    # but uncorrelated daily returns
    dates = pd.date_range("2024-01-01", periods=10, freq="D")
    df_prices = pd.DataFrame(
        {
            "AAA": [100, 101, 100, 102, 101, 103, 102, 104, 103, 105],
            "BBB": [200, 198, 202, 200, 204, 202, 206, 204, 208, 206],
        },
        index=dates,
    )
    # yf.download multi-symbol format has MultiIndex columns ('Close', 'AAA'), ('Close', 'BBB')
    multi_df = pd.concat({"Close": df_prices}, axis=1)

    with patch("sqlite3.connect") as mock_conn, \
         patch("pandas.read_sql") as mock_read_sql, \
         patch("yfinance.download") as mock_yf:

        mock_read_sql.return_value = pd.DataFrame({"symbol": ["AAA", "BBB"]})
        mock_yf.return_value = multi_df

        res = calculate_portfolio_correlation()
        assert "high_corr_count" in res
        assert res["symbols_analyzed"] == 2


def test_pit_q4_lag():
    # Q4 (March 31) gets 60 days lag
    march_q4_lag = _get_lag_for_metric("earnings", report_date="2024-03-31")
    assert march_q4_lag.days == 60

    # Q2 (September 30) gets standard 45 days lag
    sept_q2_lag = _get_lag_for_metric("earnings", report_date="2024-09-30")
    assert sept_q2_lag.days == 45


def test_roe_clamping_and_equity_floor():
    with patch("modules.adapters.nse_xbrl_provider._NSE_XBRL_AVAILABLE", True), \
         patch.dict("os.environ", {"NSE_COOKIE": "dummy"}):
        provider = NSEXBRLProvider()

        mock_client = MagicMock()
        mock_client._get.return_value = {"info": {"companyName": "Test Equity Ltd"}}

        # Filing with negative equity -> should set ROE to None
        negative_eq_filings = [LocalFilingMock(date(2024, 3, 31), bs_equity=-100.0, q_pat=20.0)] * 4
        mock_client.fetch_financials.return_value = negative_eq_filings
        provider._client = mock_client

        res = provider._fetch_sync("TEST.NS")
        assert res["ROE%"] is None
        # Q4 March filing -> As_Of_Date should be 60 days post 2024-03-31 (2024-05-30)
        assert res["As_Of_Date"] == "2024-05-30"


def test_turnaround_growth():
    # Negative base PAT (-50) to positive PAT (+100) across 3 years
    turnaround_val = _turnaround_growth(start_val=-50.0, end_val=100.0, years=3)
    assert turnaround_val is not None
    assert turnaround_val > 0.0

    series = {"2021": -50.0, "2022": 10.0, "2023": 50.0, "2024": 100.0}
    cagrs = _cagr_from_series(series, {"3Y": 3})
    assert cagrs["3Y"] is not None
    assert cagrs["3Y"] > 0.0


def test_liquidity_verified_volume():
    with patch("scripts.internal.liquidity_simulator.get_jugaad_history") as mock_jugaad:
        mock_jugaad.side_effect = Exception("Fetch failed")
        avg_vol, price, is_verified = _fetch_recent_volume_and_price("TEST.NS")
        assert avg_vol == 100000.0
        assert price == 0.0
        assert is_verified is False


def test_pit_q4_lag_never_shortens_a_stricter_baseline():
    # Earnings base (45d) -> Q4 override raises to 60d
    assert _get_lag_for_metric("earnings", report_date="2024-03-31").days == 60
    # Balance sheet base (60d) -> Q4 override keeps 60d
    assert _get_lag_for_metric("balance_sheet", report_date="2024-03-31").days == 60
    # Cashflow base (75d) -> Q4 override MUST NOT shorten to 60d; must remain 75d
    assert _get_lag_for_metric("cashflow", report_date="2024-03-31").days == 75
    # Default base (45d) -> Q4 override raises to 60d
    assert _get_lag_for_metric("custom_metric", report_date="2024-03-31").days == 60
    # Non-March filing retains base lag
    assert _get_lag_for_metric("cashflow", report_date="2024-09-30").days == 75


def test_turnaround_growth_reaches_yfinance_production_path():
    # Time-series with negative start_val (-50 -> 100 over 3 periods)
    s = pd.Series([-50.0, 10.0, 50.0, 100.0], index=pd.date_range("2021", periods=4, freq="YE"))
    res = _compute_multi_period_cagr(s, {"3Y": 3})
    assert res["3Y"] is not None
    assert res["3Y"] > 0.0
