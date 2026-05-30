# tests/test_pit_gate_integration.py
"""
Integration test: enforce_pit_gate is called from the main scoring path.

Proves that calculate_institutional_score() raises PITViolationError
when stock data has a quarter-end date within the SEBI 45-day filing lag.
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.pit_auditor import PITViolationError
from modules.scoring import calculate_institutional_score


def _stock_with_pit_dates(as_of: str, quarter_end: str) -> dict:
    """Minimal stock dict with PIT date fields."""
    return {
        "Symbol": "PITTEST.NS",
        "Sector": "Technology",
        "As_Of_Date": as_of,
        "Quarter_End": quarter_end,
    }


class TestPITGateIntegration:
    """Verify the scoring engine enforces PIT gate for fresh filings."""

    def test_score_raises_for_30_day_old_filing(self):
        """Stock with quarter ending 30 days ago must be blocked (< 45 days)."""
        today = date.today()
        quarter_end = (today - timedelta(days=30)).isoformat()
        as_of = today.isoformat()
        data = _stock_with_pit_dates(as_of=as_of, quarter_end=quarter_end)
        with pytest.raises(PITViolationError, match="PIT BLOCK"):
            calculate_institutional_score(data)

    def test_score_passes_for_60_day_old_filing(self):
        """Stock with quarter ending 60 days ago must pass the gate."""
        today = date.today()
        quarter_end = (today - timedelta(days=60)).isoformat()
        as_of = today.isoformat()
        data = _stock_with_pit_dates(as_of=as_of, quarter_end=quarter_end)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)

    def test_score_without_pit_fields_skips_gate(self):
        """Stock data without Quarter_End/As_Of_Date must not trigger the gate."""
        data = {"Symbol": "NOPIT.NS", "Sector": "Finance"}
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)

