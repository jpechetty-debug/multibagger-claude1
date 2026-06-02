"""Tests for sector-aware DQ limits in dq_gates.py.

Verifies that sector-specific limits override flat METRIC_LIMITS,
unknown sectors fall back to defaults, and validate_dataframe
applies per-sector validation.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _inject_sector_cache(cache: dict) -> None:
    """Directly inject a sector limit cache into dq_gates for testing."""
    from modules.data_layer import dq_gates
    dq_gates._sector_limits_cache = cache
    dq_gates._cache_loaded = True


def _reset_cache() -> None:
    from modules.data_layer import dq_gates
    dq_gates._sector_limits_cache = {}
    dq_gates._cache_loaded = False


@pytest.fixture(autouse=True)
def _clean_cache():
    """Reset the sector cache before and after each test."""
    _reset_cache()
    yield
    _reset_cache()


# ── Build test caches ─────────────────────────────────────────────────────────

def _make_banking_cache():
    from modules.data_layer.dq_gates import MetricLimit
    return {
        "Banking": {
            "pe_ratio": MetricLimit("pe_ratio", -20, 40, None),
            "debt_equity": MetricLimit("debt_equity", 0, 20, None),
            "roe": MetricLimit("roe", -50, 100, None),
        }
    }


def _make_it_cache():
    from modules.data_layer.dq_gates import MetricLimit
    return {
        "IT": {
            "pe_ratio": MetricLimit("pe_ratio", -20, 120, None),
            "debt_equity": MetricLimit("debt_equity", 0, 5, None),
        }
    }


def _make_metals_cache():
    from modules.data_layer.dq_gates import MetricLimit
    return {
        "Metals": {
            "pe_ratio": MetricLimit("pe_ratio", -100, 100, None),
        }
    }


def _make_multi_sector_cache():
    from modules.data_layer.dq_gates import MetricLimit
    return {
        "Banking": {
            "pe_ratio": MetricLimit("pe_ratio", -20, 40, None),
            "debt_equity": MetricLimit("debt_equity", 0, 20, None),
        },
        "IT": {
            "pe_ratio": MetricLimit("pe_ratio", -20, 120, None),
            "debt_equity": MetricLimit("debt_equity", 0, 5, None),
        },
        "Metals": {
            "pe_ratio": MetricLimit("pe_ratio", -100, 100, None),
        },
    }


# ── validate_record tests ────────────────────────────────────────────────────


class TestValidateRecordSectorAware:
    """Test that validate_record uses sector-specific limits when provided."""

    def test_banking_pe_not_clamped(self):
        """Banking PE of 8 is normal and should pass without clamping."""
        _inject_sector_cache(_make_banking_cache())
        from modules.data_layer.dq_gates import validate_record

        row = {"symbol": "HDFCBANK", "pe_ratio": 8.0}
        sanitized, flags = validate_record(row, sector="Banking")

        assert sanitized["pe_ratio"] == 8.0
        assert not any("pe_ratio" in f for f in flags)

    def test_banking_pe_clamped_high(self):
        """Banking PE of 50 should be clamped to 40 under Banking limits."""
        _inject_sector_cache(_make_banking_cache())
        from modules.data_layer.dq_gates import validate_record

        row = {"symbol": "HDFCBANK", "pe_ratio": 50.0}
        sanitized, flags = validate_record(row, sector="Banking")

        assert sanitized["pe_ratio"] == 40.0
        assert "pe_ratio_clamped_high" in flags

    def test_it_high_pe_passes(self):
        """IT stock with PE=80 should pass under IT sector limits."""
        _inject_sector_cache(_make_it_cache())
        from modules.data_layer.dq_gates import validate_record

        row = {"symbol": "TCS", "pe_ratio": 80.0}
        sanitized, flags = validate_record(row, sector="IT")

        assert sanitized["pe_ratio"] == 80.0
        assert not any("pe_ratio" in f for f in flags)

    def test_metals_suspicious_pe_clamped(self):
        """Metals stock with PE=200 should be clamped to 100 under Metals limits."""
        _inject_sector_cache(_make_metals_cache())
        from modules.data_layer.dq_gates import validate_record

        row = {"symbol": "TATASTEEL", "pe_ratio": 200.0}
        sanitized, flags = validate_record(row, sector="Metals")

        assert sanitized["pe_ratio"] == 100.0
        assert "pe_ratio_clamped_high" in flags

    def test_banking_high_debt_equity_passes(self):
        """Banking D/E of 12 is normal for banks and should not be clamped."""
        _inject_sector_cache(_make_banking_cache())
        from modules.data_layer.dq_gates import validate_record

        row = {"symbol": "SBIN", "debt_equity": 12.0}
        sanitized, flags = validate_record(row, sector="Banking")

        assert sanitized["debt_equity"] == 12.0
        assert not any("debt_equity" in f for f in flags)

    def test_fallback_to_flat_limits_unknown_sector(self):
        """Unknown sector uses flat METRIC_LIMITS — PE of 800 passes under flat max of 1000."""
        _inject_sector_cache(_make_banking_cache())
        from modules.data_layer.dq_gates import validate_record

        row = {"symbol": "OBSCURE", "pe_ratio": 800.0}
        sanitized, flags = validate_record(row, sector="UnknownSector")

        assert sanitized["pe_ratio"] == 800.0
        assert not any("pe_ratio" in f for f in flags)

    def test_no_sector_uses_flat_limits(self):
        """When no sector is provided, flat limits apply (backward compatible)."""
        _inject_sector_cache(_make_banking_cache())
        from modules.data_layer.dq_gates import validate_record

        row = {"symbol": "TEST", "pe_ratio": 800.0}
        sanitized, flags = validate_record(row, sector=None)

        assert sanitized["pe_ratio"] == 800.0
        assert not any("pe_ratio" in f for f in flags)

    def test_provider_sector_aliases_hit_seeded_limits(self):
        """Provider labels are canonicalized before sector-limit lookup."""
        _inject_sector_cache(_make_multi_sector_cache())
        from modules.data_layer.dq_gates import validate_record

        it, _ = validate_record(
            {"symbol": "TCS", "pe_ratio": 150.0},
            sector="Information Technology",
        )
        bank, _ = validate_record(
            {"symbol": "HDFCBANK", "pe_ratio": 50.0},
            sector="Banking (PVT)",
        )
        metal, _ = validate_record(
            {"symbol": "TATASTEEL", "pe_ratio": 150.0},
            sector="Metals & Mining",
        )

        assert it["pe_ratio"] == 120.0
        assert bank["pe_ratio"] == 40.0
        assert metal["pe_ratio"] == 100.0


# ── validate_dataframe tests ──────────────────────────────────────────────────


class TestValidateDataframeSectorAware:
    """Test that validate_dataframe applies per-sector limits when sector column exists."""

    def test_mixed_sectors_different_limits(self):
        """Banking and IT stocks in same DF get different PE limits applied."""
        _inject_sector_cache(_make_multi_sector_cache())
        from modules.data_layer.dq_gates import validate_dataframe

        df = pd.DataFrame([
            {"symbol": "HDFCBANK", "sector": "Banking", "pe_ratio": 50.0, "score": 80},
            {"symbol": "TCS", "sector": "IT", "pe_ratio": 80.0, "score": 85},
            {"symbol": "TATASTEEL", "sector": "Metals", "pe_ratio": 150.0, "score": 70},
            {"symbol": "OBSCURE", "sector": "Unknown", "pe_ratio": 800.0, "score": 60},
        ])

        result = validate_dataframe(df)

        # Banking: PE 50 clamped to 40
        assert result.loc[result["symbol"] == "HDFCBANK", "pe_ratio"].iloc[0] == 40.0
        # IT: PE 80 within range, not clamped
        assert result.loc[result["symbol"] == "TCS", "pe_ratio"].iloc[0] == 80.0
        # Metals: PE 150 clamped to 100
        assert result.loc[result["symbol"] == "TATASTEEL", "pe_ratio"].iloc[0] == 100.0
        # Unknown sector: falls back to flat limit (max 1000), PE 800 passes
        assert result.loc[result["symbol"] == "OBSCURE", "pe_ratio"].iloc[0] == 800.0

    def test_no_sector_column_uses_flat(self):
        """Without sector column, flat limits apply (backward compatible)."""
        _inject_sector_cache(_make_banking_cache())
        from modules.data_layer.dq_gates import validate_dataframe

        df = pd.DataFrame([
            {"symbol": "TEST", "pe_ratio": 800.0, "score": 80},
        ])

        result = validate_dataframe(df)

        # Flat limit max is 1000, so 800 passes
        assert result.loc[0, "pe_ratio"] == 800.0

    def test_data_quality_score_computed(self):
        """Data quality scores are computed even with sector-aware limits."""
        _inject_sector_cache(_make_multi_sector_cache())
        from modules.data_layer.dq_gates import validate_dataframe

        df = pd.DataFrame([
            {"symbol": "HDFCBANK", "sector": "Banking", "pe_ratio": 8.0, "score": 80},
        ])

        result = validate_dataframe(df)

        assert "data_quality" in result.columns
        assert result.loc[0, "data_quality"] == 100.0

    def test_mock_history_penalty_preserved(self):
        """Mock history penalty still works with sector-aware limits."""
        _inject_sector_cache(_make_banking_cache())
        from modules.data_layer.dq_gates import validate_dataframe

        df = pd.DataFrame([
            {
                "symbol": "HDFCBANK",
                "sector": "Banking",
                "pe_ratio": 8.0,
                "score": 80,
                "data_quality_flags": "mock_history",
            },
        ])

        result = validate_dataframe(df)
        assert result.loc[0, "data_quality"] <= 50.0

    def test_sector_aware_debt_equity(self):
        """Banking D/E=12 passes; IT D/E=12 gets clamped to 5."""
        _inject_sector_cache(_make_multi_sector_cache())
        from modules.data_layer.dq_gates import validate_dataframe

        df = pd.DataFrame([
            {"symbol": "HDFCBANK", "sector": "Banking", "debt_equity": 12.0, "score": 80},
            {"symbol": "TCS", "sector": "IT", "debt_equity": 12.0, "score": 85},
        ])

        result = validate_dataframe(df)

        # Banking: D/E 12 within range (max 20)
        assert result.loc[result["symbol"] == "HDFCBANK", "debt_equity"].iloc[0] == 12.0
        # IT: D/E 12 clamped to 5
        assert result.loc[result["symbol"] == "TCS", "debt_equity"].iloc[0] == 5.0


# ── Cache behavior tests ─────────────────────────────────────────────────────


class TestSectorCacheBehavior:
    """Test cache loading mechanics."""

    def test_cache_loaded_flag_prevents_reload(self):
        """Once _cache_loaded is True, load_sector_limits() is a no-op."""
        from modules.data_layer import dq_gates

        dq_gates._cache_loaded = True
        dq_gates._sector_limits_cache = {"TestSector": {}}

        # Should not modify cache since it's already loaded
        with patch("modules.data_layer.dq_gates.logger") as mock_logger:
            dq_gates.load_sector_limits()

        assert "TestSector" in dq_gates._sector_limits_cache

    def test_clear_cache_resets_state(self):
        """clear_sector_cache resets both cache dict and loaded flag."""
        from modules.data_layer.dq_gates import clear_sector_cache

        _inject_sector_cache(_make_banking_cache())

        from modules.data_layer import dq_gates
        assert dq_gates._cache_loaded is True
        assert len(dq_gates._sector_limits_cache) > 0

        clear_sector_cache()

        assert dq_gates._cache_loaded is False
        assert len(dq_gates._sector_limits_cache) == 0

    def test_db_unavailable_falls_back_gracefully(self):
        """If DB connection fails, cache stays empty and flat limits apply."""
        from modules.data_layer import dq_gates

        _reset_cache()

        with patch("modules.data_layer.dq_gates.load_sector_limits") as mock_load:
            # Simulate: load_sector_limits sets _cache_loaded but leaves cache empty
            def side_effect():
                dq_gates._cache_loaded = True
            mock_load.side_effect = side_effect

            row = {"symbol": "TEST", "pe_ratio": 800.0}
            sanitized, flags = dq_gates.validate_record(row)

            assert sanitized["pe_ratio"] == 800.0

    def test_deduplicate_existing_flags(self):
        """Verify that pre-existing flags are deduplicated and new flags don't duplicate existing ones."""
        from modules.data_layer.dq_gates import validate_dataframe

        # DF has pre-existing duplicate flags, and some NaN fields that will trigger "invalid" flags
        df = pd.DataFrame([
            {
                "symbol": "TEST",
                "sector": "Banking",
                "pe_ratio": None,  # triggers pe_ratio_invalid
                "score": 80,
                "data_quality_flags": "pe_ratio_invalid,mock_history,pe_ratio_invalid",
            }
        ])

        result = validate_dataframe(df)
        flags = result.loc[0, "data_quality_flags"]

        # Ensure order is preserved and duplicates are cleaned up
        assert flags == "pe_ratio_invalid,mock_history"

    def test_calculate_institutional_score_sector_aware(self):
        """Verify that calculate_institutional_score validates inputs using the sector."""
        _inject_sector_cache(_make_banking_cache())
        from modules.scoring import calculate_institutional_score

        # PE of 50 for Banking should get clamped to 40, whereas PE of 50 for IT (with max 120) should not
        banking_stock = {
            "Symbol": "HDFCBANK",
            "Sector": "Banking",
            "PE_Ratio": 50.0,
            "ROE%": 18.0,
            "Sales_Growth_5Y%": 15.0,
            "Debt_Equity": 2.0,
            "CFO_PAT_Ratio": 1.2,
            "F_Score": 8,
            "Price": 1400.0,
            "ATR": 30.0,
            "RS_Rating": 1.0,
            "Down_From_52W_High%": 10.0,
        }

        # Let's mock news sentiment to avoid yfinance/web requests
        with patch("modules.news_sentiment.engine.get_alpha_signal") as mock_signal:
            mock_signal.return_value = {"sentiment_score": 0.5}

            # PE=50 gets clamped to 40 under Banking limits
            res_50 = calculate_institutional_score(banking_stock)

            # PE=40 is already at the Banking ceiling — no clamping
            res_40 = calculate_institutional_score({**banking_stock, "PE_Ratio": 40.0})

            # PE=500 is extreme but should also clamp to 40 for Banking
            res_extreme = calculate_institutional_score(
                {**banking_stock, "PE_Ratio": 500.0}
            )

            # All three should produce identical scores because sector
            # limits clamp PE to 40 for Banking in every case.
            assert res_50["total_score"] == res_40["total_score"], (
                f"PE=50 score {res_50['total_score']} != PE=40 score {res_40['total_score']}"
            )
            assert res_extreme["total_score"] == res_40["total_score"], (
                f"PE=500 score {res_extreme['total_score']} != PE=40 score {res_40['total_score']}"
            )
