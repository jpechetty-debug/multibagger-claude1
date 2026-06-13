"""Tests for Phase 3: Analytical Engine & Multi-Tier Screening.

Covers:
  - Module 3.1: Sector-Relative SQL Builder (build_sector_relative_filter)
  - Module 3.2: Earnings Velocity Evaluator (_margin_expansion_slope / analyze_quarterly_trends)
  - Module 3.3: Friction-Aware Liquidity Filter (liquidity_gate)
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ── Module 3.1: Sector-Relative SQL Builder ────────────────────────────────────


class TestBuildSectorRelativeFilter:
    """Tests for build_sector_relative_filter in fundamental_filters.py."""

    SECTOR_MEDIANS = {
        "IT": {"median_roe": 20.0, "median_growth": 15.0, "median_pe": 30.0},
        "Banking": {"median_roe": 12.0, "median_growth": 10.0, "median_pe": 15.0},
    }

    def _make_stock(self, sector, roe=None, growth=None, pe=None, symbol="TEST"):
        stock = {"Sector": sector, "Symbol": symbol}
        if roe is not None:
            stock["Avg_ROE_5Y%"] = roe
        if growth is not None:
            stock["Sales_Growth_5Y%"] = growth
        if pe is not None:
            stock["PE_Ratio"] = pe
        return stock

    def test_stock_beats_all_three_metrics(self):
        from modules.fundamental_filters import build_sector_relative_filter

        # ROE 30 >= 20*1.2=24 ✓, Growth 25 >= 15*1.2=18 ✓, PE 20 <= 30/1.2=25 ✓
        stock = self._make_stock("IT", roe=30, growth=25, pe=20)
        result = build_sector_relative_filter([stock], self.SECTOR_MEDIANS)
        assert len(result) == 1
        assert "roe" in result[0]["sector_relative_pass"]
        assert "growth" in result[0]["sector_relative_pass"]
        assert "pe" in result[0]["sector_relative_pass"]

    def test_stock_beats_two_of_three(self):
        from modules.fundamental_filters import build_sector_relative_filter

        # ROE 30 ✓, Growth 25 ✓, PE 35 > 25 ✗
        stock = self._make_stock("IT", roe=30, growth=25, pe=35)
        result = build_sector_relative_filter([stock], self.SECTOR_MEDIANS)
        assert len(result) == 1
        assert "pe" not in result[0]["sector_relative_pass"]

    def test_stock_fails_only_one_metric(self):
        from modules.fundamental_filters import build_sector_relative_filter

        # ROE 30 ✓, Growth 10 < 18 ✗, PE 35 > 25 ✗ => only 1 beat
        stock = self._make_stock("IT", roe=30, growth=10, pe=35)
        result = build_sector_relative_filter([stock], self.SECTOR_MEDIANS)
        assert len(result) == 0

    def test_unknown_sector_skipped(self):
        from modules.fundamental_filters import build_sector_relative_filter

        stock = self._make_stock("Aerospace", roe=99, growth=99, pe=1)
        result = build_sector_relative_filter([stock], self.SECTOR_MEDIANS)
        assert len(result) == 0

    def test_custom_outperformance_ratio(self):
        from modules.fundamental_filters import build_sector_relative_filter

        # At 50% outperformance: ROE threshold = 20*1.5=30, Growth = 15*1.5=22.5
        stock = self._make_stock("IT", roe=28, growth=20, pe=10)
        # Fails at 50%
        result = build_sector_relative_filter(
            [stock], self.SECTOR_MEDIANS, outperformance_ratio=1.50
        )
        assert len(result) == 0
        # Passes at 20%
        result = build_sector_relative_filter(
            [stock], self.SECTOR_MEDIANS, outperformance_ratio=1.20
        )
        assert len(result) == 1

    def test_min_metrics_to_beat_override(self):
        from modules.fundamental_filters import build_sector_relative_filter

        # Only ROE passes
        stock = self._make_stock("IT", roe=30, growth=5, pe=50)
        result = build_sector_relative_filter(
            [stock], self.SECTOR_MEDIANS, min_metrics_to_beat=1
        )
        assert len(result) == 1

    def test_empty_input(self):
        from modules.fundamental_filters import build_sector_relative_filter

        result = build_sector_relative_filter([], self.SECTOR_MEDIANS)
        assert result == []


# ── Module 3.2: Earnings Velocity Evaluator ────────────────────────────────────


class TestMarginExpansionSlope:
    """Tests for _margin_expansion_slope and earnings_velocity_positive."""

    def test_expanding_margins_positive_slope(self):
        from modules.quarterly_results import _margin_expansion_slope

        quarters = [
            {"margin": 10.0},
            {"margin": 12.0},
            {"margin": 14.0},
            {"margin": 16.0},
        ]
        slope = _margin_expansion_slope(quarters)
        assert slope > 0, f"Expected positive slope, got {slope}"

    def test_contracting_margins_negative_slope(self):
        from modules.quarterly_results import _margin_expansion_slope

        quarters = [
            {"margin": 20.0},
            {"margin": 18.0},
            {"margin": 15.0},
            {"margin": 12.0},
        ]
        slope = _margin_expansion_slope(quarters)
        assert slope < 0, f"Expected negative slope, got {slope}"

    def test_flat_margins_zero_slope(self):
        from modules.quarterly_results import _margin_expansion_slope

        quarters = [
            {"margin": 15.0},
            {"margin": 15.0},
            {"margin": 15.0},
            {"margin": 15.0},
        ]
        slope = _margin_expansion_slope(quarters)
        assert slope == 0.0

    def test_insufficient_data_returns_zero(self):
        from modules.quarterly_results import _margin_expansion_slope

        assert _margin_expansion_slope([{"margin": 10.0}]) == 0.0
        assert _margin_expansion_slope([{"margin": 10.0}, {"margin": 12.0}]) == 0.0

    def test_analyze_quarterly_trends_includes_slope(self):
        from modules.quarterly_results import analyze_quarterly_trends

        quarters = [
            {
                "revenue": 100, "profit": 10, "ebitda": 20,
                "margin": 10.0, "ebitda_margin": 20.0, "eps": 1.0,
                "revenue_growth_qoq": 5.0, "profit_growth_qoq": 5.0,
                "revenue_growth_yoy": None, "profit_growth_yoy": None,
            },
            {
                "revenue": 110, "profit": 13, "ebitda": 23,
                "margin": 11.8, "ebitda_margin": 20.9, "eps": 1.1,
                "revenue_growth_qoq": 10.0, "profit_growth_qoq": 30.0,
                "revenue_growth_yoy": None, "profit_growth_yoy": None,
            },
            {
                "revenue": 120, "profit": 16, "ebitda": 26,
                "margin": 13.3, "ebitda_margin": 21.7, "eps": 1.2,
                "revenue_growth_qoq": 9.1, "profit_growth_qoq": 23.1,
                "revenue_growth_yoy": None, "profit_growth_yoy": None,
            },
            {
                "revenue": 130, "profit": 20, "ebitda": 30,
                "margin": 15.4, "ebitda_margin": 23.1, "eps": 1.4,
                "revenue_growth_qoq": 8.3, "profit_growth_qoq": 25.0,
                "revenue_growth_yoy": None, "profit_growth_yoy": None,
            },
        ]
        trends = analyze_quarterly_trends(quarters)
        assert "margin_expansion_slope" in trends
        assert "earnings_velocity_positive" in trends
        assert trends["margin_expansion_slope"] > 0
        assert trends["earnings_velocity_positive"] is True


# ── Module 3.3: Friction-Aware Liquidity Filter ───────────────────────────────


class TestLiquidityGate:
    """Tests for liquidity_gate in slippage.py."""

    def test_mega_liquid_passes(self):
        from modules.risk.slippage import liquidity_gate

        passes, slippage, reason = liquidity_gate(100000, 600)
        assert passes is True
        assert slippage <= 0.5
        assert "Tier 1" in reason

    def test_large_cap_passes(self):
        from modules.risk.slippage import liquidity_gate

        passes, slippage, reason = liquidity_gate(50000, 150)
        assert passes is True
        assert slippage <= 0.5

    def test_mid_cap_fails_default_threshold(self):
        from modules.risk.slippage import liquidity_gate

        # Mid cap: impact=0.5 + base=0.1 = 0.6 > 0.5 default
        passes, slippage, reason = liquidity_gate(5000, 15)
        assert passes is False
        assert slippage > 0.5

    def test_small_cap_fails(self):
        from modules.risk.slippage import liquidity_gate

        passes, slippage, reason = liquidity_gate(500, 3)
        assert passes is False
        assert slippage > 0.5

    def test_micro_cap_trap(self):
        from modules.risk.slippage import liquidity_gate

        passes, slippage, reason = liquidity_gate(50, 0.5)
        assert passes is False
        assert "Micro" in reason

    def test_custom_threshold_relaxed(self):
        from modules.risk.slippage import liquidity_gate

        # Mid cap (0.6% slippage) passes with 1% threshold
        passes, slippage, reason = liquidity_gate(5000, 15, max_slippage_pct=1.0)
        assert passes is True

    def test_returns_exact_slippage_value(self):
        from modules.risk.slippage import liquidity_gate

        _, slippage, _ = liquidity_gate(100000, 600)
        # Tier 1: base 0.1 + impact 0.1 = 0.2
        assert slippage == 0.2
