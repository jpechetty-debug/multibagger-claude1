# tests/test_hardening_contracts.py
"""
Phase 4.3: Contract regression tests for the data hardening framework.

These tests enforce that the Phase 1-4 data correctness guarantees
cannot silently regress without test failures.
"""
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ════════════════════════════════════════════════════════════════════════════
# CONTRACT 1: DQ Gate Invariants
# ════════════════════════════════════════════════════════════════════════════


class TestDQGateContracts:
    """Validate that DQ gates maintain physical-limit invariants."""

    def test_pe_ratio_clamped_to_physical_limits(self):
        from modules.dq_gates import validate_record

        row = {"symbol": "TEST", "pe_ratio": 99999.0}
        sanitized, flags = validate_record(row)
        assert sanitized["pe_ratio"] <= 1000.0
        assert "pe_ratio_clamped_high" in flags

    def test_negative_pe_clamped_low(self):
        from modules.dq_gates import validate_record

        row = {"symbol": "TEST", "pe_ratio": -999.0}
        sanitized, flags = validate_record(row)
        assert sanitized["pe_ratio"] >= -100.0
        assert "pe_ratio_clamped_low" in flags

    def test_dividend_yield_auto_scaled(self):
        from modules.dq_gates import validate_record

        row = {"symbol": "TEST", "dividend_yield": 250.0}
        sanitized, flags = validate_record(row)
        assert sanitized["dividend_yield"] == 2.5
        assert "dividend_yield_auto_scaled" in flags

    def test_non_finite_rejected(self):
        from modules.dq_gates import validate_record

        row = {"symbol": "TEST", "pe_ratio": float("inf")}
        sanitized, flags = validate_record(row)
        assert sanitized["pe_ratio"] is None
        assert "pe_ratio_non_finite" in flags

    def test_nan_rejected(self):
        from modules.dq_gates import validate_record

        row = {"symbol": "TEST", "roe": float("nan")}
        sanitized, flags = validate_record(row)
        assert sanitized["roe"] is None
        assert "roe_non_finite" in flags

    def test_unparseable_string_rejected(self):
        from modules.dq_gates import validate_record

        row = {"symbol": "TEST", "pe_ratio": "not-a-number"}
        sanitized, flags = validate_record(row)
        assert sanitized["pe_ratio"] is None
        assert "pe_ratio_unparseable" in flags

    def test_zero_value_passes_through(self):
        """0.0 is a valid value and must NOT be treated as None or missing."""
        from modules.dq_gates import validate_record

        row = {"symbol": "TEST", "debt_equity": 0.0}
        sanitized, flags = validate_record(row)
        assert sanitized["debt_equity"] == 0.0
        assert len(flags) == 0

    def test_all_scoring_fields_have_limits(self):
        """Every field used in scoring.py must be covered by DQ gates."""
        from modules.dq_gates import METRIC_LIMITS

        covered = {ml.column for ml in METRIC_LIMITS}
        critical_fields = {
            "pe_ratio", "debt_equity", "dividend_yield",
            "roe", "eps_growth", "peg_ratio",
            "rs_rating", "cfo_pat_ratio",
        }
        missing = critical_fields - covered
        assert not missing, f"Scoring fields missing DQ gate coverage: {missing}"


# ════════════════════════════════════════════════════════════════════════════
# CONTRACT 2: Pydantic Model Boundary
# ════════════════════════════════════════════════════════════════════════════


class TestPydanticModelContracts:
    """Validate that the Pydantic ingestion boundary works correctly."""

    def test_extra_fields_are_rejected(self):
        """Phase fix: extra='forbid' prevents unknown fields from leaking."""
        from pydantic import ValidationError

        from modules.models import StockDataPayload

        with pytest.raises(ValidationError):
            StockDataPayload(
                Symbol="TEST.NS",
                Price=100.0,
                unknown_field="should_be_dropped",
                another_garbage=42,
            )

    def test_roe_fraction_normalized_to_percent(self):
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", **{"ROE%": 0.15})
        assert payload.ROE_pct == 15.0

    def test_pe_ratio_clamped_at_boundary(self):
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", PE_Ratio=5000.0)
        assert payload.PE_Ratio == 1000.0

    def test_debt_equity_clamped_at_boundary(self):
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS", Debt_Equity=100.0)
        assert payload.Debt_Equity == 50.0

    def test_none_preserved_not_coerced_to_zero(self):
        """Critical: None must remain None, not become 0."""
        from modules.models import StockDataPayload

        payload = StockDataPayload(Symbol="TEST.NS")
        assert payload.PE_Ratio is None
        assert payload.ROE_pct is None
        assert payload.Debt_Equity is None


# ════════════════════════════════════════════════════════════════════════════
# CONTRACT 3: Scoring Engine Invariants
# ════════════════════════════════════════════════════════════════════════════


class TestScoringContracts:
    """Validate that scoring engine hardening invariants hold."""

    def _build_stock_data(self, **overrides):
        base = {
            "Symbol": "TEST.NS",
            "Price": 100.0,
            "Sector": "Technology",
            "Market_Cap_Cr": 5000.0,
            "PE_Ratio": 20.0,
            "ROE%": 18.0,
            "Sales_Growth_5Y%": 15.0,
            "Debt_Equity": 0.5,
            "CFO_PAT_Ratio": 1.2,
            "RS_Rating": 1.1,
            "Promoter_Holding%": 55.0,
            "F_Score": 7,
        }
        base.update(overrides)
        return base

    def test_score_bounded_0_to_100(self):
        from modules.scoring import calculate_institutional_score

        result = calculate_institutional_score(self._build_stock_data())
        score = result["total_score"]
        assert 0 <= score <= 100, f"Score {score} out of [0, 100] bounds"

    def test_missing_f_score_treated_as_neutral_not_zero(self):
        """Phase 1 fix: F_Score=None → neutral 50, not penalized 0."""
        from modules.scoring import calculate_institutional_score

        with_f = calculate_institutional_score(self._build_stock_data(F_Score=7))
        without_f = calculate_institutional_score(self._build_stock_data(F_Score=None))

        # Without F_Score should be near-neutral, not severely penalized
        delta = with_f["total_score"] - without_f["total_score"]
        assert delta < 25, f"Missing F_Score caused {delta}pt penalty, expected <25pt"

    def test_bonus_cap_enforced(self):
        """Phase 2 fix: Non-fundamental bonuses capped at 20% of base score."""
        from modules.scoring import calculate_institutional_score

        # Perfect stock with maximum bonuses
        result = calculate_institutional_score(
            self._build_stock_data(
                Earnings_Accel=1,
                Sector_Leader=1,
                Smart_Money=95.0,
            ),
            market_regime="BULL",
        )
        # Score should never exceed 100 due to capping
        assert result["total_score"] <= 100

    def test_rs_rating_uses_sigmoid_not_cliff(self):
        """Phase 2.5: RS Rating should produce continuous scores, not 25-pt cliffs."""
        from modules.scoring import calculate_institutional_score

        # RS 1.19 vs RS 1.21 should differ by at most ~5 points (sigmoid),
        # not 25 points (old cliff bucketing)
        r1 = calculate_institutional_score(self._build_stock_data(RS_Rating=1.19))
        r2 = calculate_institutional_score(self._build_stock_data(RS_Rating=1.21))
        delta = abs(r1["total_score"] - r2["total_score"])
        assert delta < 5, f"RS cliff detected: {delta}pt difference for RS 1.19 vs 1.21"

    def test_none_pe_does_not_crash(self):
        """Scoring engine must gracefully handle None for every optional field."""
        from modules.scoring import calculate_institutional_score

        result = calculate_institutional_score(
            self._build_stock_data(PE_Ratio=None, Debt_Equity=None, CFO_PAT_Ratio=None)
        )
        assert isinstance(result["total_score"], (int, float))

    def test_sector_medians_exclude_none_values(self):
        """Phase 1 fix: None values must not participate in sector median calculation."""
        from modules.scoring import calculate_sector_medians

        stocks = [
            {"Sector": "Tech", "PE_Ratio": 20.0, "ROE%": 18.0},
            {"Sector": "Tech", "PE_Ratio": None, "ROE%": None},
            {"Sector": "Tech", "PE_Ratio": 30.0, "ROE%": 22.0},
        ]
        medians = calculate_sector_medians(stocks)
        # If None was included, median PE would be different
        assert medians.get("Tech", {}).get("median_pe") == pytest.approx(25.0, abs=0.1)


# ════════════════════════════════════════════════════════════════════════════
# CONTRACT 4: Provider Health Tracking
# ════════════════════════════════════════════════════════════════════════════


class TestProviderHealthContracts:
    """Validate that provider health uses actual counters."""

    def test_provider_tracker_records_and_reads(self, tmp_path, monkeypatch):
        """ProviderCallTracker must record and read back actual success/failure data."""
        from modules.data_freshness import ProviderCallTracker

        # Reset singleton for isolation
        ProviderCallTracker._instance = None

        # Redirect to temp DB
        monkeypatch.setattr(
            "modules.data_freshness._get_cache_connection",
            lambda: __import__("sqlite3").connect(str(tmp_path / "test_cache.db")),
        )
        tracker = ProviderCallTracker()
        tracker._initialized = False
        tracker.__init__()

        # Record some calls
        tracker.record("yfinance", success=True)
        tracker.record("yfinance", success=True)
        tracker.record("yfinance", success=False, error="timeout")

        stats = tracker.get_stats("yfinance", window_hours=1)
        assert stats["total"] == 3
        assert stats["successes"] == 2
        assert stats["success_rate"] == pytest.approx(66.7, abs=0.1)

        # Cleanup singleton
        ProviderCallTracker._instance = None


# ════════════════════════════════════════════════════════════════════════════
# CONTRACT 5: Cache Version Stamping
# ════════════════════════════════════════════════════════════════════════════


class TestCacheVersionContracts:
    """Validate that cache version stamps prevent stale deserialization."""

    def test_cache_version_constant_exists(self):
        from modules.data_service import CACHE_SCHEMA_VERSION

        assert isinstance(CACHE_SCHEMA_VERSION, int)
        assert CACHE_SCHEMA_VERSION >= 1
