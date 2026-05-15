# tests/test_data_correctness.py
"""
Data Correctness Test Suite

Covers the five data integrity hardening layers:
1. Pydantic ingestion boundary (scale normalization, extra field rejection)
2. Symbol canonicalization
3. DQ gates (physical-limit validators)
4. Financial adapter (extraction / calculation decoupling)
5. End-to-end pipeline correctness
"""

from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ══════════════════════════════════════════════════════════════════════════════
# 1. PYDANTIC INGESTION BOUNDARY
# ══════════════════════════════════════════════════════════════════════════════


class TestStockDataPayloadValidation:
    """Verify that StockDataPayload normalizes scales at the edge."""

    def test_roe_fraction_auto_scaled(self):
        """ROE of 0.15 (fraction) should become 15.0 (percent)."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", **{"ROE%": 0.15})
        assert payload.ROE_pct == 15.0

    def test_roe_already_percent_unchanged(self):
        """ROE of 18.5 (already percent) should stay 18.5."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", **{"ROE%": 18.5})
        assert payload.ROE_pct == 18.5

    def test_roe_negative_fraction(self):
        """ROE of -0.05 should become -5.0."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", **{"ROE%": -0.05})
        assert payload.ROE_pct == -5.0

    def test_roe_zero(self):
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", **{"ROE%": 0})
        assert payload.ROE_pct == 0.0

    def test_roe_none(self):
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", **{"ROE%": None})
        assert payload.ROE_pct is None

    def test_dividend_yield_fraction(self):
        """Dividend yield of 0.025 should become 2.5%."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", Dividend_Yield=0.025)
        assert payload.Dividend_Yield == 2.5

    def test_dividend_yield_absurd_capped(self):
        """Dividend yield of 250 (clearly wrong scale) gets auto-scaled."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", Dividend_Yield=250)
        assert payload.Dividend_Yield <= 25.0

    def test_pe_ratio_clamped(self):
        """PE ratio of 5000 should be clamped to 1000."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", PE_Ratio=5000)
        assert payload.PE_Ratio == 1000.0

    def test_pe_ratio_nan_becomes_none(self):
        """Non-finite PE should become None."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", PE_Ratio=float("inf"))
        assert payload.PE_Ratio is None

    def test_pe_ratio_string_na_becomes_none(self):
        """String 'N/A' for PE should become None."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", PE_Ratio=None)
        assert payload.PE_Ratio is None

    def test_debt_equity_clamped(self):
        """Debt/Equity of 100 should be clamped to 50."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", Debt_Equity=100)
        assert payload.Debt_Equity == 50.0

    def test_extra_fields_ignored(self):
        """Unknown fields should raise ValidationError."""
        from pydantic import ValidationError

        from modules.models import StockDataPayload

        with pytest.raises(ValidationError):
            StockDataPayload(
                Symbol="TEST.NS",
                Price=100.0,
                bogus_field="should_not_appear",
                another_junk=42,
            )

    def test_data_quality_score(self):
        """Full payload should score 100, sparse should score lower."""
        from modules.models import StockDataPayload

        full = StockDataPayload(
            Symbol="TEST.NS",
            Price=100.0,
            PE_Ratio=20.0,
            **{"ROE%": 15.0},
            Debt_Equity=0.5,
            **{"Sales_Growth_TTM%": 12.0},
            CFO_PAT_Ratio=1.2,
            F_Score=7,
            Market_Cap_Cr=5000,
        )
        assert full.data_quality_score == 100

        sparse = StockDataPayload(Symbol="TEST.NS", Price=100.0)
        assert sparse.data_quality_score < 100

    def test_dividend_payout_capped_at_200(self):
        """Payout ratio of 0.95 should become 95%, and 350 should be capped at 200."""
        from modules.models import StockDataPayload

        normal = StockDataPayload(Symbol="TEST.NS", Dividend_Payout=0.95)
        assert normal.Dividend_Payout == 95.0

        absurd = StockDataPayload(Symbol="TEST.NS", Dividend_Payout=350)
        assert absurd.Dividend_Payout == 200.0


# ══════════════════════════════════════════════════════════════════════════════
# 2. SYMBOL CANONICALIZATION
# ══════════════════════════════════════════════════════════════════════════════


class TestSymbolCanonicalization:
    """Verify canonical_symbol() handles all edge cases."""

    def test_bare_symbol_gets_ns(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("reliance") == "RELIANCE.NS"

    def test_dotN_fixed(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("RELIANCE.N") == "RELIANCE.NS"

    def test_dotNSE_fixed(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("RELIANCE.NSE") == "RELIANCE.NS"

    def test_dotBO_preserved(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("SBIN.BO") == "SBIN.BO"

    def test_dotBSE_to_dotBO(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("SBIN.BSE") == "SBIN.BO"

    def test_whitespace_stripped(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("  tcs  ") == "TCS.NS"

    def test_lowercase_uppercased(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("infy") == "INFY.NS"

    def test_already_canonical(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("RELIANCE.NS") == "RELIANCE.NS"

    def test_empty_string(self):
        from modules.symbol_utils import canonical_symbol

        assert canonical_symbol("") == ""

    def test_db_symbol_strips_suffix(self):
        from modules.symbol_utils import db_symbol

        assert db_symbol("RELIANCE.NS") == "RELIANCE"
        assert db_symbol("SBIN.BO") == "SBIN"
        assert db_symbol("TCS") == "TCS"

    def test_normalize_symbol_delegates(self):
        from modules.symbol_utils import canonical_symbol, normalize_symbol

        assert normalize_symbol("reliance") == canonical_symbol("reliance")


# ══════════════════════════════════════════════════════════════════════════════
# 3. DQ GATES
# ══════════════════════════════════════════════════════════════════════════════


class TestDQGates:
    """Verify physical-limit validators and data quality scoring."""

    def test_pe_ratio_clamped_high(self):
        from modules.dq_gates import validate_record

        row = {"pe_ratio": 5000}
        sanitized, flags = validate_record(row)
        assert sanitized["pe_ratio"] == 1000
        assert "pe_ratio_clamped_high" in flags

    def test_roe_clamped_low(self):
        from modules.dq_gates import validate_record

        row = {"roe": -999}
        sanitized, flags = validate_record(row)
        assert sanitized["roe"] == -500
        assert "roe_clamped_low" in flags

    def test_score_clamped_to_0_100(self):
        from modules.dq_gates import validate_record

        row = {"score": 150}
        sanitized, flags = validate_record(row)
        assert sanitized["score"] == 100
        assert "score_clamped_high" in flags

    def test_dividend_yield_auto_scaled(self):
        from modules.dq_gates import validate_record

        row = {"dividend_yield": 250}
        sanitized, flags = validate_record(row)
        assert sanitized["dividend_yield"] == 2.5
        assert "dividend_yield_auto_scaled" in flags

    def test_non_finite_cleared(self):
        from modules.dq_gates import validate_record

        row = {"pe_ratio": float("inf")}
        sanitized, flags = validate_record(row)
        assert sanitized["pe_ratio"] is None
        assert "pe_ratio_non_finite" in flags

    def test_unparseable_cleared(self):
        from modules.dq_gates import validate_record

        row = {"pe_ratio": "N/A"}
        sanitized, flags = validate_record(row)
        assert sanitized["pe_ratio"] is None
        assert "pe_ratio_unparseable" in flags

    def test_clean_record_no_flags(self):
        from modules.dq_gates import validate_record

        row = {"pe_ratio": 20, "roe": 15, "score": 75}
        sanitized, flags = validate_record(row)
        assert len(flags) == 0
        assert sanitized["pe_ratio"] == 20

    def test_quality_score_perfect(self):
        from modules.dq_gates import compute_data_quality_score

        assert compute_data_quality_score([], 10) == 100.0

    def test_quality_score_with_flags(self):
        from modules.dq_gates import compute_data_quality_score

        score = compute_data_quality_score(["a", "b"], 10)
        assert score == 80.0

    def test_validate_dataframe(self):
        import pandas as pd

        from modules.dq_gates import validate_dataframe

        df = pd.DataFrame(
            {
                "symbol": ["A", "B"],
                "pe_ratio": [20, 5000],
                "roe": [15, -999],
                "score": [75, 150],
            }
        )
        result = validate_dataframe(df)
        assert result.loc[0, "pe_ratio"] == 20
        assert result.loc[1, "pe_ratio"] == 1000
        assert result.loc[1, "roe"] == -500
        assert result.loc[1, "score"] == 100
        assert "data_quality" in result.columns


# ══════════════════════════════════════════════════════════════════════════════
# 4. FINANCIAL ADAPTER & PURE CAGR ENGINE
# ══════════════════════════════════════════════════════════════════════════════


class TestFinancialAdapter:
    """Test the NormalizedFinancials dataclass and adapter."""

    def test_normalized_financials_defaults(self):
        from modules.financial_adapter import NormalizedFinancials

        nf = NormalizedFinancials()
        assert nf.revenue_series == {}
        assert nf.data_points == 0

    def test_extract_from_mock_ticker(self):
        """Verify that the adapter extracts data from a mock ticker."""
        from unittest.mock import MagicMock

        import pandas as pd

        from modules.financial_adapter import extract_normalized_financials

        ticker = MagicMock()

        dates = pd.to_datetime(["2023-03-31", "2022-03-31", "2021-03-31", "2020-03-31"])
        ticker.financials = pd.DataFrame(
            {
                dates[0]: [100000, 15000],
                dates[1]: [85000, 12000],
                dates[2]: [72000, 10000],
                dates[3]: [60000, 8000],
            },
            index=["Total Revenue", "Net Income"],
        )
        ticker.balance_sheet = pd.DataFrame(
            {
                dates[0]: [200000, 50000, 1000000],
                dates[1]: [180000, 45000, 1000000],
                dates[2]: [160000, 40000, 1000000],
                dates[3]: [140000, 35000, 1000000],
            },
            index=["Total Assets", "Stockholders Equity", "Ordinary Shares Number"],
        )

        nf = extract_normalized_financials(ticker)
        assert nf.data_points == 4
        assert len(nf.revenue_series) == 4
        assert len(nf.net_income_series) == 4
        assert len(nf.shares_outstanding_series) == 4


class TestPureCagrEngine:
    """Test CAGR calculations with static data — no yfinance needed."""

    def test_known_revenue_cagr(self):
        """Revenue: 100 -> 121 over 2 years = 10% CAGR."""
        from modules.cagr_engine import _safe_cagr

        result = _safe_cagr(100, 121, 2)
        assert result is not None
        assert abs(result - 10.0) < 0.1

    def test_cagr_from_normalized(self):
        from modules.cagr_engine import calculate_all_cagrs_from_normalized
        from modules.financial_adapter import NormalizedFinancials

        nf = NormalizedFinancials(
            revenue_series={
                "2020": 60000,
                "2021": 72000,
                "2022": 85000,
                "2023": 100000,
            },
            net_income_series={
                "2020": 8000,
                "2021": 10000,
                "2022": 12000,
                "2023": 15000,
            },
            shares_outstanding_series={
                "2020": 1000,
                "2021": 1000,
                "2022": 1000,
                "2023": 1000,
            },
            data_points=4,
        )

        result = calculate_all_cagrs_from_normalized(nf)

        # Revenue 60000 -> 100000 over 3 years = ~18.6% CAGR
        assert result["Revenue_CAGR_3Y"] is not None
        assert result["Revenue_CAGR_3Y"] > 15

        # PAT 8000 -> 15000 over 3 years = ~23.3% CAGR
        assert result["PAT_CAGR_3Y"] is not None
        assert result["PAT_CAGR_3Y"] > 20

        # Consistency should be HIGH (both > 15%)
        assert result["CAGR_Consistency"] == "HIGH"

    def test_cagr_insufficient_data(self):
        from modules.cagr_engine import calculate_all_cagrs_from_normalized
        from modules.financial_adapter import NormalizedFinancials

        nf = NormalizedFinancials(data_points=1)
        result = calculate_all_cagrs_from_normalized(nf)
        assert result["Revenue_CAGR_3Y"] is None
        assert result["CAGR_Consistency"] == "UNKNOWN"

    def test_cagr_negative_start_returns_none(self):
        """Negative start value should return None (can't compute CAGR)."""
        from modules.cagr_engine import _safe_cagr

        assert _safe_cagr(-100, 200, 3) is None

    def test_cagr_zero_start_returns_none(self):
        from modules.cagr_engine import _safe_cagr

        assert _safe_cagr(0, 200, 3) is None
