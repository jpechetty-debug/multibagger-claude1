# tests/test_data_freshness_gate.py
"""
Data freshness hard gate — scoring engine integration tests.

Verifies that calculate_institutional_score() enforces MAX_FUNDAMENTAL_AGE_DAYS
and emits stale_data warnings for the 60–90 day window.
"""
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.errors import SovereignErrorExc
from modules.scoring import calculate_institutional_score


def _stock_with_age(days_old: int) -> dict:
    """Minimal stock dict with As_Of_Date set to `days_old` days ago."""
    as_of = (date.today() - timedelta(days=days_old)).isoformat()
    return {
        "Symbol": "FRESH.NS",
        "Sector": "Technology",
        "As_Of_Date": as_of,
        # Quarter_End far in the past so PIT gate won't interfere
        "Quarter_End": "2020-03-31",
    }


class TestDataFreshnessGate:
    """Verify the scoring engine enforces data freshness constraints."""

    def test_89_day_old_data_passes(self):
        """89 days is within the 90-day hard limit — score should succeed."""
        data = _stock_with_age(89)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)

    def test_91_day_old_data_raises_stale_error(self):
        """91 days exceeds the 90-day hard limit — must raise SovereignErrorExc."""
        data = _stock_with_age(91)
        with pytest.raises(SovereignErrorExc) as exc_info:
            calculate_institutional_score(data)
        assert exc_info.value.error_code == "STALE_DATA"
        assert exc_info.value.details["age_days"] == 91

    def test_65_day_old_data_passes_with_stale_flag(self):
        """65 days crosses the 60-day warning threshold — flag but don't block."""
        data = _stock_with_age(65)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)
        assert "stale_data" in result["data_quality_flags"]

    def test_missing_as_of_date_skips_check(self):
        """When As_Of_Date is absent, freshness check is skipped entirely."""
        data = {"Symbol": "NODATE.NS", "Sector": "Finance"}
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)
        assert "stale_data" not in result.get("data_quality_flags", [])

    def test_30_day_old_data_no_flag(self):
        """30-day data is fresh — no stale_data flag expected."""
        data = _stock_with_age(30)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)
        assert "stale_data" not in result.get("data_quality_flags", [])

    def test_custom_threshold_via_env(self):
        """MAX_FUNDAMENTAL_AGE_DAYS can be overridden via config."""
        data = _stock_with_age(50)
        with patch("modules.scoring.engine.MAX_FUNDAMENTAL_AGE_DAYS", 45):
            with pytest.raises(SovereignErrorExc) as exc_info:
                calculate_institutional_score(data)
            assert exc_info.value.error_code == "STALE_DATA"
