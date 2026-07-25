import asyncio
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from modules.adapters.nse_xbrl_provider import (
    NSEXBRLProvider,
    _clean_symbol,
    _resolve_issuer_name,
    _ttm_growth_pct,
    _ttm_pair,
    _ttm_sum,
)


class MockFilingResult:
    def __init__(
        self,
        period_end: date,
        is_consolidated: bool = True,
        q_revenue: float = 100.0,
        q_pat: float = 20.0,
        q_diluted_eps: float = 2.0,
        bs_equity: float = 500.0,
        debt_equity_ratio: float = 0.4,
        book_value_per_share: float = 50.0,
        is_audited: bool = True,
        seq_id: str = "SEQ123",
    ):
        self.period_end = period_end
        self.is_consolidated = is_consolidated
        self.q_revenue = q_revenue
        self.q_pat = q_pat
        self.q_diluted_eps = q_diluted_eps
        self.bs_equity = bs_equity
        self.debt_equity_ratio = debt_equity_ratio
        self.book_value_per_share = book_value_per_share
        self.is_audited = is_audited
        self.seq_id = seq_id


def test_clean_symbol():
    assert _clean_symbol("RELIANCE.NS") == "RELIANCE"
    assert _clean_symbol("tcs.bo ") == "TCS"
    assert _clean_symbol("INFY.BSE") == "INFY"
    assert _clean_symbol(" HDFCBANK ") == "HDFCBANK"


def test_ttm_helpers():
    # Helper requires 8 filings for _ttm_pair and _ttm_growth_pct
    incomplete_filings = [MockFilingResult(date(2024, 3, 31))] * 5
    assert _ttm_pair(incomplete_filings, "q_revenue") is None
    assert _ttm_growth_pct(incomplete_filings, "q_revenue") is None
    assert _ttm_sum(incomplete_filings[:3], "q_pat") is None

    # Complete 8 filings (recent 4: 100 each = 400; prior 4: 50 each = 200)
    recent_dates = [date(2024, 3, 31), date(2023, 12, 31), date(2023, 9, 30), date(2023, 6, 30)]
    prior_dates = [date(2023, 3, 31), date(2022, 12, 31), date(2022, 9, 30), date(2022, 6, 30)]
    recent_4 = [MockFilingResult(d, q_revenue=100.0, q_diluted_eps=2.0, q_pat=25.0) for d in recent_dates]
    prior_4 = [MockFilingResult(d, q_revenue=50.0, q_diluted_eps=1.0, q_pat=12.5) for d in prior_dates]
    full_8 = recent_4 + prior_4

    assert _ttm_pair(full_8, "q_revenue") == (400.0, 200.0)
    assert _ttm_growth_pct(full_8, "q_revenue") == 100.0  # (400-200)/200 * 100
    assert _ttm_growth_pct(full_8, "q_diluted_eps") == 100.0
    assert _ttm_sum(full_8, "q_pat") == 100.0  # sum of recent 4 (4 * 25.0)


def test_resolve_issuer_name():
    mock_client = MagicMock()
    mock_client._get.return_value = {"info": {"companyName": "Reliance Industries Limited"}}
    assert _resolve_issuer_name(mock_client, "RELIANCE") == "Reliance Industries Limited"

    # Test error fallback
    mock_client._get.side_effect = Exception("Network error")
    assert _resolve_issuer_name(mock_client, "RELIANCE") is None

    # Test missing payload fallback
    mock_client._get.side_effect = None
    mock_client._get.return_value = {}
    assert _resolve_issuer_name(mock_client, "RELIANCE") is None


def test_provider_availability_without_cookie():
    with patch.dict(os.environ, {}, clear=True):
        provider = NSEXBRLProvider()
        assert not provider.available

        with pytest.raises(RuntimeError, match="NSEXBRLProvider not available"):
            asyncio.run(provider.fetch_fundamentals("RELIANCE.NS"))


def test_provider_fetch_sync_success():
    with patch("modules.adapters.nse_xbrl_provider._NSE_XBRL_AVAILABLE", True), \
         patch.dict(os.environ, {"NSE_COOKIE": "dummy_cookie"}):
        provider = NSEXBRLProvider()
        assert provider.available

        mock_client = MagicMock()
        mock_client._get.return_value = {"info": {"companyName": "Reliance Industries Limited"}}

        recent_4 = [
            MockFilingResult(
                date(2024, 3, 31),
                is_consolidated=True,
                q_revenue=100.0,
                q_pat=25.0,
                q_diluted_eps=2.0,
                bs_equity=500.0,
                debt_equity_ratio=0.35,
                book_value_per_share=120.0,
            ),
            MockFilingResult(date(2023, 12, 31), is_consolidated=True, q_revenue=100.0, q_pat=25.0, q_diluted_eps=2.0),
            MockFilingResult(date(2023, 9, 30), is_consolidated=True, q_revenue=100.0, q_pat=25.0, q_diluted_eps=2.0),
            MockFilingResult(date(2023, 6, 30), is_consolidated=True, q_revenue=100.0, q_pat=25.0, q_diluted_eps=2.0),
        ]
        prior_4 = [
            MockFilingResult(date(2023, 3, 31), is_consolidated=True, q_revenue=80.0, q_pat=20.0, q_diluted_eps=1.6),
            MockFilingResult(date(2022, 12, 31), is_consolidated=True, q_revenue=80.0, q_pat=20.0, q_diluted_eps=1.6),
            MockFilingResult(date(2022, 9, 30), is_consolidated=True, q_revenue=80.0, q_pat=20.0, q_diluted_eps=1.6),
            MockFilingResult(date(2022, 6, 30), is_consolidated=True, q_revenue=80.0, q_pat=20.0, q_diluted_eps=1.6),
        ]
        filings = recent_4 + prior_4
        mock_client.fetch_financials.return_value = filings

        provider._client = mock_client
        res = provider._fetch_sync("RELIANCE.NS")

        assert res["Symbol"] == "RELIANCE.NS"
        assert res["source"] == "nse_xbrl"
        assert res["Debt_Equity"] == 0.35
        assert res["Book_Value"] == 120.0
        assert res["ROE%"] == 20.0  # TTM PAT = 100.0 / bs_equity 500.0 * 100 = 20%
        assert res["Sales_Growth_TTM%"] == 25.0  # (400 - 320)/320 * 100 = 25%
        assert res["EPS_Growth%"] == 25.0
        assert res["Quarter_End"] == "2024-03-31"
        assert res["As_Of_Date"] == "2024-05-30"  # 2024-03-31 + 60 days (March quarter-end -> annual-results lag)
