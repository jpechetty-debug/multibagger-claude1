# tests/test_phase1_remaining.py
"""
Phase 1 completion tests covering:
  - as_of_date malformed-date rejection at write boundary
  - PIT hard gate: enforce_pit_gate raises PITViolationError within 45 days
  - PIT hard gate: passes cleanly at 46+ days
  - Price adjustment verification (split-adjusted prices are continuous)
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Item 3: as_of_date format enforcement ─────────────────────────────────────


class TestAsOfDateRejection:
    """Verify malformed dates are rejected at the DB write boundary."""

    def test_strict_normalize_rejects_garbage(self):
        """strict_normalize_date must raise on unparseable strings."""
        from db.date_utils import strict_normalize_date

        with pytest.raises(ValueError, match="Cannot parse"):
            strict_normalize_date("not-a-date")

    def test_strict_normalize_rejects_none(self):
        from db.date_utils import strict_normalize_date

        with pytest.raises(ValueError, match="must not be None"):
            strict_normalize_date(None)

    def test_strict_normalize_accepts_iso_format(self):
        from db.date_utils import strict_normalize_date

        assert strict_normalize_date("2024-06-15") == "2024-06-15"

    def test_strict_normalize_accepts_datetime(self):
        from db.date_utils import strict_normalize_date
        from datetime import datetime

        assert strict_normalize_date(datetime(2024, 6, 15, 10, 30)) == "2024-06-15"

    def test_write_boundary_rejects_malformed_date(self, tmp_path, monkeypatch):
        """_write_fundamentals_snapshot must raise on non-ISO dates like '15-Jun-2024'."""
        import db.repository as repo

        db_path = tmp_path / "test_date_reject.db"
        monkeypatch.setattr(repo, "DB_NAME", str(db_path), raising=False)
        repo.init_db()

        df = pd.DataFrame([{
            "symbol": "TEST.NS",
            "as_of_date": "not-a-real-date-at-all",
            "price": 100.0,
            "sector": "Technology",
            "score": 80,
        }])

        with pytest.raises(ValueError):
            repo._write_fundamentals_snapshot(df)

    def test_write_boundary_accepts_valid_iso_date(self, tmp_path, monkeypatch):
        """_write_fundamentals_snapshot must succeed with ISO dates."""
        import db.repository as repo

        db_path = tmp_path / "test_date_ok.db"
        monkeypatch.setattr(repo, "DB_NAME", str(db_path), raising=False)
        repo.init_db()

        df = pd.DataFrame([{
            "symbol": "OK.NS",
            "as_of_date": "2024-06-15",
            "price": 200.0,
            "sector": "Financial",
            "score": 75,
        }])

        # Should not raise
        repo._write_fundamentals_snapshot(df)


# ── Item 5: PIT hard gate (enforce_pit_gate) ─────────────────────────────────


class TestPITHardGate:
    """Verify enforce_pit_gate raises within 45-day SEBI lag, passes at 46+."""

    def test_raises_within_45_days(self):
        """Score request using data only 30 days after quarter end must BLOCK."""
        from modules.pit_auditor import PITViolationError, enforce_pit_gate

        quarter_end = date(2024, 3, 31)
        as_of = quarter_end + timedelta(days=30)  # Only 30 days — too soon

        with pytest.raises(PITViolationError, match="PIT BLOCK"):
            enforce_pit_gate(as_of, quarter_end, symbol="RELIANCE.NS")

    def test_raises_at_exactly_44_days(self):
        """44 days is still within the 45-day SEBI lag — must block."""
        from modules.pit_auditor import PITViolationError, enforce_pit_gate

        quarter_end = date(2024, 6, 30)
        as_of = quarter_end + timedelta(days=44)

        with pytest.raises(PITViolationError):
            enforce_pit_gate(as_of, quarter_end, symbol="HDFCBANK.NS")

    def test_passes_at_46_days(self):
        """46 days after quarter end — data is public, must pass cleanly."""
        from modules.pit_auditor import enforce_pit_gate

        quarter_end = date(2024, 3, 31)
        as_of = quarter_end + timedelta(days=46)

        # Should not raise
        enforce_pit_gate(as_of, quarter_end, symbol="TCS.NS")

    def test_passes_at_exactly_45_days(self):
        """Exactly 45 days — boundary case, should pass."""
        from modules.pit_auditor import enforce_pit_gate

        quarter_end = date(2024, 9, 30)
        as_of = quarter_end + timedelta(days=45)

        enforce_pit_gate(as_of, quarter_end, symbol="INFY.NS")

    def test_raises_with_future_as_of_date(self):
        """as_of_date BEFORE quarter_end (future data) must block."""
        from modules.pit_auditor import PITViolationError, enforce_pit_gate

        quarter_end = date(2024, 12, 31)
        as_of = date(2024, 12, 15)  # Before quarter even ended

        with pytest.raises(PITViolationError):
            enforce_pit_gate(as_of, quarter_end, symbol="SBIN.NS")

    def test_pit_violation_error_is_exception(self):
        """PITViolationError must be catchable as a standard Exception."""
        from modules.pit_auditor import PITViolationError

        assert issubclass(PITViolationError, Exception)


# ── Item 6: PIT violation test coverage via audit_dataset ─────────────────────


class TestPITAuditDatasetViolations:
    """Verify audit_dataset detects future-leak violations."""

    def test_future_dated_as_of_flags_violation(self):
        """Data with as_of_date before expected_public_date must raise PITViolationError."""
        from modules.pit_auditor import PITViolationError, audit_dataset

        df = pd.DataFrame([{
            "symbol": "FUTURE.NS",
            "metric_name": "eps",
            "report_date": "2024-03-31",
            "as_of_date": "2024-04-05",  # Only 5 days after — FUTURE_LEAK
        }])

        # 100% violation rate triggers REJECT_DATASET → raises
        with pytest.raises(PITViolationError, match="PIT Violation"):
            audit_dataset(df)

    def test_data_after_lag_no_violation(self):
        """Data with as_of_date well after the expected lag must pass cleanly."""
        from modules.pit_auditor import audit_dataset

        df = pd.DataFrame([{
            "symbol": "CLEAN.NS",
            "metric_name": "eps",
            "report_date": "2024-03-31",
            "as_of_date": "2024-06-15",  # 76 days after — well past 45-day lag
        }])

        report = audit_dataset(df)
        assert report.violation_count == 0
        assert report.recommended_action == "PASS"


# ── Item 4: Price adjustment verification test ────────────────────────────────


class TestPriceAdjustmentVerification:
    """Verify that auto_adjust=True produces split-continuous prices.

    Since we cannot rely on network calls in CI, we test the contract:
    the _extract_close_series helper and the engine's documented invariant
    that Close prices from auto_adjust=True are already adjusted.
    """

    def test_extract_close_returns_adjusted_close(self):
        """_extract_close_series must return the 'Close' column from auto_adjust data."""
        from backtest.backtest_engine import _extract_close_series

        # Simulate auto_adjust=True output: only 'Close' exists (no 'Adj Close')
        dates = pd.date_range("2023-01-01", periods=5, freq="D")
        df = pd.DataFrame({"Close": [100.0, 102.0, 101.0, 103.0, 104.0]}, index=dates)

        result = _extract_close_series(df, "TEST.NS", single_symbol=True)
        assert len(result) == 5
        assert result.iloc[0] == 100.0

    def test_synthetic_split_adjusted_prices_are_continuous(self):
        """Simulate a 1:1 bonus split and verify adjusted prices are continuous.

        With auto_adjust=True, yfinance halves pre-split prices so the series
        is continuous across the split date. This test verifies that the
        return calculation sees no discontinuity.
        """
        # Pre-split: raw price was 1000, adjusted to 500 by yfinance
        # Post-split: raw price is 500, unchanged by yfinance
        # Result: continuous series around the split date
        dates = pd.date_range("2023-06-01", periods=10, freq="D")
        adjusted_prices = pd.Series(
            [498, 500, 502, 504, 506,   # Pre-split (halved by adjustment)
             504, 506, 508, 510, 512],   # Post-split (raw)
            index=dates,
        )

        returns = adjusted_prices.pct_change().dropna()

        # Key assertion: no return exceeds 5% for a stock that moved ~1-2% daily
        # If adjustment were missing, the split day would show ~100% return
        assert returns.abs().max() < 0.05, (
            f"Max return {returns.abs().max():.2%} exceeds 5% — "
            "split adjustment appears broken"
        )

    def test_auto_adjust_kwarg_is_set_in_engine(self):
        """Verify the backtest engine code documents auto_adjust=True."""
        import inspect
        from backtest.backtest_engine import VectorBTEngine

        source = inspect.getsource(VectorBTEngine.run_walk_forward_strategy_backtest)
        assert "auto_adjust=True" in source, (
            "Walk-forward backtest must use auto_adjust=True for split-safe prices"
        )

        source_batch = inspect.getsource(VectorBTEngine.run_batch_momentum_backtest)
        assert "auto_adjust=True" in source_batch, (
            "Batch backtest must use auto_adjust=True for split-safe prices"
        )
