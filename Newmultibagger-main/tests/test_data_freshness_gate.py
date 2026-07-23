# tests/test_data_freshness_gate.py
"""
Data freshness soft gate - scoring engine integration tests.

Verifies that calculate_institutional_score() applies a staleness penalty
when data exceeds MAX_FUNDAMENTAL_AGE_DAYS and emits stale_data warnings
for the 60-90 day window.
"""

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.scoring import calculate_institutional_score  # noqa: E402


def _stock_with_age(days_old: int) -> dict:
    """Minimal stock dict with As_Of_Date set to days_old days ago."""
    as_of = (date.today() - timedelta(days=days_old)).isoformat()
    return {
        "Symbol": "FRESH.NS",
        "Sector": "Technology",
        "As_Of_Date": as_of,
        "Quarter_End": "2020-03-31",
    }


class TestDataFreshnessGate:
    """Verify the scoring engine enforces data freshness constraints."""

    def test_89_day_old_data_passes(self):
        data = _stock_with_age(89)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)

    def test_91_day_old_data_scores_with_penalty(self):
        """Soft gate: stale data still scores but gets penalised and flagged."""
        data = _stock_with_age(91)
        result = calculate_institutional_score(data)
        # Should still produce a numeric score (not blocked)
        assert isinstance(result["total_score"], int | float)
        # Should be flagged as stale
        assert "stale_data" in result["data_quality_flags"]
        # Scoring strategy should indicate degraded
        assert result["scoring_strategy"] == "STALE_DATA_DEGRADED"
        # Should have a STALE_DATA_PENALTY in factor audit
        penalty_names = [p["name"] for p in result["factor_penalties"]]
        assert "STALE_DATA_PENALTY" in penalty_names

    def test_91_day_old_data_penalty_magnitude(self):
        """1 day over threshold → -21 penalty (base 20 + 1 extra day)."""
        data = _stock_with_age(91)
        result = calculate_institutional_score(data)
        stale_penalty = [
            p for p in result["factor_penalties"]
            if p["name"] == "STALE_DATA_PENALTY"
        ]
        assert len(stale_penalty) == 1
        assert stale_penalty[0]["value"] == -21.0

    def test_140_day_old_data_hits_penalty_cap(self):
        """50 days over threshold → capped at -50 penalty."""
        data = _stock_with_age(140)
        result = calculate_institutional_score(data)
        stale_penalty = [
            p for p in result["factor_penalties"]
            if p["name"] == "STALE_DATA_PENALTY"
        ]
        assert len(stale_penalty) == 1
        assert stale_penalty[0]["value"] == -50.0

    def test_65_day_old_data_passes_with_stale_flag(self):
        data = _stock_with_age(65)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)
        assert "stale_data" in result["data_quality_flags"]

    def test_missing_as_of_date_skips_check(self):
        data = {"Symbol": "NODATE.NS", "Sector": "Finance"}
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)
        assert "stale_data" not in result.get("data_quality_flags", [])

    def test_30_day_old_data_no_flag(self):
        data = _stock_with_age(30)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)
        assert "stale_data" not in result.get("data_quality_flags", [])

    def test_custom_threshold_via_env(self):
        """With a lower threshold, data beyond it gets degraded scoring."""
        data = _stock_with_age(50)
        with patch("modules.scoring.engine.MAX_FUNDAMENTAL_AGE_DAYS", 45):
            result = calculate_institutional_score(data)
            assert result["scoring_strategy"] == "STALE_DATA_DEGRADED"
            assert "stale_data" in result["data_quality_flags"]
            penalty_names = [p["name"] for p in result["factor_penalties"]]
            assert "STALE_DATA_PENALTY" in penalty_names
