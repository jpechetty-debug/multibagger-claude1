"""tests/test_factor_staleness.py

Tests for worker.tasks.check_factor_data_freshness.

All filesystem and webhook I/O is mocked — no network, no real CSV required.

Covers:
  - fresh CSV: returns {"status": "fresh"}, no _log.critical, no dispatch
  - stale CSV: returns {"status": "stale"}, _log.critical fired, dispatch called
  - missing CSV: same stale path with missing_columns = all FACTOR_COLUMNS
  - dispatch failure: caught, task still returns stale status (no re-raise)
  - DATA_STALE in _VALID_EVENT_TYPES
  - /api/factor-exposure/meta returns correct staleness flag
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_fresh_csv(tmp_path: Path, days_old: int = 5) -> Path:
    """Write a minimal factor CSV with `days_old` age."""
    csv = tmp_path / "india_factor_returns.csv"
    last_date = date.today() - timedelta(days=days_old)
    df = pd.DataFrame(
        {
            "date": pd.date_range(end=last_date, periods=10, freq="W-MON").strftime(
                "%Y-%m-%d"
            ),
            "nifty_market": [0.01] * 10,
            "size": [0.005] * 10,
            "value": [-0.003] * 10,
            "momentum": [0.012] * 10,
            "quality": [0.008] * 10,
            "low_vol": [0.004] * 10,
        }
    )
    df.to_csv(csv, index=False)
    return csv


def _stub_task_imports(monkeypatch, tmp_path: Path, days_old: int):
    """Patch india_factor_loader constants to use tmp_path CSV."""
    csv = _make_fresh_csv(tmp_path, days_old=days_old)

    import modules.india_factor_loader as ldr

    monkeypatch.setattr(ldr, "FACTOR_CSV_PATH", csv)
    ldr._load_raw.cache_clear()
    return csv


# ── Task: fresh data ──────────────────────────────────────────────────────────

class TestCheckFactorDataFreshnessFresh:

    def test_fresh_csv_returns_status_fresh(self, tmp_path, monkeypatch):
        _stub_task_imports(monkeypatch, tmp_path, days_old=5)

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks._dispatch_factor_alert", new_callable=AsyncMock) as mock_dispatch:
            result = check_factor_data_freshness()

        assert result["status"] == "fresh"
        mock_dispatch.assert_not_called()

    def test_fresh_csv_no_critical_log(self, tmp_path, monkeypatch):
        _stub_task_imports(monkeypatch, tmp_path, days_old=5)

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks.logger") as mock_log:
            with patch("worker.tasks._dispatch_factor_alert", new_callable=AsyncMock):
                check_factor_data_freshness()

        mock_log.critical.assert_not_called()


# ── Task: stale data ──────────────────────────────────────────────────────────

class TestCheckFactorDataFreshnessStale:

    def test_stale_csv_returns_status_stale(self, tmp_path, monkeypatch):
        _stub_task_imports(monkeypatch, tmp_path, days_old=50)
        monkeypatch.setenv("FACTOR_STALENESS_DAYS", "45")

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks._dispatch_factor_alert", new_callable=AsyncMock):
            result = check_factor_data_freshness()

        assert result["status"] == "stale"
        assert result["age_days"] >= 50
        assert result["threshold_days"] == 45

    def test_stale_csv_fires_critical_log(self, tmp_path, monkeypatch):
        _stub_task_imports(monkeypatch, tmp_path, days_old=50)
        monkeypatch.setenv("FACTOR_STALENESS_DAYS", "45")

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks.logger") as mock_log:
            with patch("worker.tasks._dispatch_factor_alert", new_callable=AsyncMock):
                check_factor_data_freshness()

        mock_log.critical.assert_called_once()
        call_kwargs = mock_log.critical.call_args
        assert "factor_data_stale" in call_kwargs[0]

    def test_stale_csv_dispatches_webhook(self, tmp_path, monkeypatch):
        _stub_task_imports(monkeypatch, tmp_path, days_old=50)
        monkeypatch.setenv("FACTOR_STALENESS_DAYS", "45")

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks._dispatch_factor_alert", new_callable=AsyncMock) as mock_d:
            check_factor_data_freshness()

        mock_d.assert_called_once()
        payload = mock_d.call_args[0][0]
        assert len(payload) == 1
        assert payload[0]["type"] == "DATA_STALE"
        assert payload[0]["severity"] == "high"
        assert payload[0]["age_days"] >= 50

    def test_dispatch_failure_does_not_reraise(self, tmp_path, monkeypatch):
        """A broken webhook endpoint must never crash the Celery task."""
        _stub_task_imports(monkeypatch, tmp_path, days_old=60)
        monkeypatch.setenv("FACTOR_STALENESS_DAYS", "45")

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks._dispatch_factor_alert",
                   side_effect=Exception("network down")):
            # Must not raise
            result = check_factor_data_freshness()

        assert result["status"] == "stale"


# ── Task: missing CSV ─────────────────────────────────────────────────────────

class TestCheckFactorDataFreshnessMissing:

    def test_missing_csv_returns_stale_with_none_age(self, tmp_path, monkeypatch):
        import modules.india_factor_loader as ldr
        monkeypatch.setattr(ldr, "FACTOR_CSV_PATH", tmp_path / "nonexistent.csv")
        monkeypatch.setenv("FACTOR_STALENESS_DAYS", "45")

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks._dispatch_factor_alert", new_callable=AsyncMock):
            result = check_factor_data_freshness()

        assert result["status"] == "stale"
        assert result["age_days"] is None
        assert result["missing_columns"] != []

    def test_missing_csv_lists_all_factor_columns(self, tmp_path, monkeypatch):
        import modules.india_factor_loader as ldr
        from modules.india_factor_loader import FACTOR_COLUMNS

        monkeypatch.setattr(ldr, "FACTOR_CSV_PATH", tmp_path / "nonexistent.csv")

        from worker.tasks import check_factor_data_freshness

        with patch("worker.tasks._dispatch_factor_alert", new_callable=AsyncMock):
            result = check_factor_data_freshness()

        assert set(result["missing_columns"]) == set(FACTOR_COLUMNS)


# ── Webhook event type ────────────────────────────────────────────────────────

class TestDataStaleEventType:

    def test_data_stale_in_valid_event_types(self):
        """DATA_STALE must be a recognised webhook event type."""
        from app_routes.webhooks import _VALID_EVENT_TYPES
        assert "DATA_STALE" in _VALID_EVENT_TYPES

    def test_webhook_creation_accepts_data_stale_filter(self):
        """_validate_event_filter must accept DATA_STALE without raising."""
        from app_routes.webhooks import _validate_event_filter
        result = _validate_event_filter(["DATA_STALE"])
        assert result is not None
        assert "DATA_STALE" in result


# ── Celery beat schedule ──────────────────────────────────────────────────────

class TestCeleryBeatSchedule:

    def test_factor_freshness_check_in_beat_schedule(self):
        """Beat schedule must include the factor freshness task."""
        from worker.celery_app import app
        schedule = app.conf.beat_schedule
        assert "factor-freshness-check" in schedule, (
            "Add 'factor-freshness-check' to beat_schedule in worker/celery_app.py"
        )

    def test_factor_freshness_task_name(self):
        from worker.celery_app import app
        entry = app.conf.beat_schedule.get("factor-freshness-check", {})
        assert entry.get("task") == "worker.tasks.check_factor_data_freshness"

    def test_factor_freshness_on_maintenance_queue(self):
        from worker.celery_app import app
        entry = app.conf.beat_schedule.get("factor-freshness-check", {})
        assert entry.get("options", {}).get("queue") == "maintenance"


# ── /api/factor-exposure/meta staleness flag ─────────────────────────────────

class TestFactorExposureMetaEndpoint:

    def test_meta_returns_stale_true_when_stale(self, tmp_path, monkeypatch):
        """GET /api/factor-exposure/meta must report stale=True for old CSV."""
        import modules.india_factor_loader as ldr
        csv = _make_fresh_csv(tmp_path, days_old=60)
        monkeypatch.setattr(ldr, "FACTOR_CSV_PATH", csv)
        monkeypatch.setenv("FACTOR_STALENESS_DAYS", "45")
        ldr._load_raw.cache_clear()

        # Import the meta function directly (not via HTTP)
        import asyncio

        from app_routes.factor_exposure import factor_exposure_meta

        result = asyncio.run(factor_exposure_meta())

        assert result["available"] is True
        assert result["stale"] is True
        assert result["age_days"] >= 60

    def test_meta_returns_stale_false_when_fresh(self, tmp_path, monkeypatch):
        import modules.india_factor_loader as ldr
        csv = _make_fresh_csv(tmp_path, days_old=3)
        monkeypatch.setattr(ldr, "FACTOR_CSV_PATH", csv)
        monkeypatch.setenv("FACTOR_STALENESS_DAYS", "45")
        ldr._load_raw.cache_clear()

        import asyncio

        from app_routes.factor_exposure import factor_exposure_meta

        result = asyncio.run(factor_exposure_meta())

        assert result["stale"] is False
        assert result["age_days"] <= 10

    def test_meta_returns_available_false_when_csv_missing(self, tmp_path, monkeypatch):
        import modules.india_factor_loader as ldr
        monkeypatch.setattr(ldr, "FACTOR_CSV_PATH", tmp_path / "missing.csv")
        ldr._load_raw.cache_clear()

        import asyncio

        from app_routes.factor_exposure import factor_exposure_meta

        result = asyncio.run(factor_exposure_meta())

        assert result["available"] is False
        assert result["stale"] is True
        assert result["last_date"] is None

    def test_meta_includes_refresh_command(self, tmp_path, monkeypatch):
        import modules.india_factor_loader as ldr
        csv = _make_fresh_csv(tmp_path, days_old=3)
        monkeypatch.setattr(ldr, "FACTOR_CSV_PATH", csv)
        ldr._load_raw.cache_clear()

        import asyncio

        from app_routes.factor_exposure import factor_exposure_meta

        result = asyncio.run(factor_exposure_meta())

        assert "refresh_command" in result
        assert "build_india_factors" in result["refresh_command"]
