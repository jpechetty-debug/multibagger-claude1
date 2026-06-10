"""
tests/test_liquidity_sim.py
============================
Unit tests for modules/liquidity.py — simulate_liquidity() engine.

Run with:
    pytest tests/test_liquidity_sim.py -v
"""

from __future__ import annotations

import math
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from modules.liquidity import (
    analyze_liquidity,
    simulate_liquidity,
    LiquiditySimResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────────

def make_stock(price=500, avg_vol=2_000_000, atr=15):
    """Default: ADVT = 2_000_000 * 500 / 1e7 = 100 Cr → institutional grade"""
    return {
        "Symbol": "TEST",
        "Price": price,
        "Avg_Volume_10D": avg_vol,
        "ATR": atr,
    }


# ── Legacy shim: analyze_liquidity ────────────────────────────────────────

class TestAnalyzeLiquidity:
    def test_no_volume_returns_zero(self):
        score, flag, reason = analyze_liquidity({"Price": 100, "Avg_Volume_10D": 0})
        assert score == 0
        assert flag is True
        assert "Volume" in reason or "No" in reason

    def test_institutional_grade(self):
        # ADVT ≥ 100 Cr
        score, flag, reason = analyze_liquidity(make_stock(price=500, avg_vol=2_000_000))
        assert score == 100
        assert flag is False

    def test_illiquid_trap(self):
        # ADVT ≈ 0.1 Cr
        score, flag, reason = analyze_liquidity({"Price": 10, "Avg_Volume_10D": 100_000, "ATR": 2})
        assert score == 0 or score < 10
        assert flag is True

    def test_moderate_liquidity(self):
        # ADVT ≈ 2.5 Cr
        score, flag, reason = analyze_liquidity({"Price": 50, "Avg_Volume_10D": 500_000})
        assert 40 <= score <= 60

    def test_exception_returns_gracefully(self):
        score, flag, reason = analyze_liquidity({"Price": "bad", "Avg_Volume_10D": "x"})
        assert score == 0
        assert flag is True
        assert "Error" in reason


# ── Core simulator ────────────────────────────────────────────────────────

class TestSimulateLiquidity:
    def test_returns_dataclass(self):
        result = simulate_liquidity(make_stock(), position_cr=1.0)
        assert isinstance(result, LiquiditySimResult)

    def test_to_dict_has_required_keys(self):
        d = simulate_liquidity(make_stock(), position_cr=5.0).to_dict()
        assert "liquidity" in d
        assert "position_sizing" in d
        assert "slippage" in d
        assert "sizing_recommendation" in d
        assert "risk" in d

    def test_zero_position_gives_zero_slippage(self):
        result = simulate_liquidity(make_stock(), position_cr=0.0)
        assert result.entry_slippage_cr == 0.0
        assert result.roundtrip_slippage_cr == 0.0

    def test_high_liquidity_green_verdict(self):
        # Nifty-50 type stock: ADVT 100 Cr, tiny 1 Cr position, low ATR
        # ATR=5 on price=500 → spread_pct = (5/500)*100*0.25 = 0.25%
        # impact-only at 1% participation is tiny → GREEN
        result = simulate_liquidity(make_stock(price=500, avg_vol=2_000_000, atr=5), position_cr=1.0)
        assert result.verdict == "GREEN"
        assert result.entry_slippage_pct < 1.5

    def test_illiquid_stock_red_verdict(self):
        # ADVT ≈ 0.5 Cr, 5 Cr position
        illiquid = {"Symbol": "ILLIQ", "Price": 10, "Avg_Volume_10D": 500_000}
        result = simulate_liquidity(illiquid, position_cr=5.0)
        assert result.verdict == "RED"
        assert result.risk_flag is True

    def test_large_position_amber_or_red(self):
        # Good liquidity but oversized position (50 Cr into 100 Cr ADVT stock)
        result = simulate_liquidity(make_stock(), position_cr=50.0)
        assert result.verdict in ("AMBER", "RED")
        assert result.participation_rate >= 0.5

    def test_days_to_build_scales_with_position(self):
        small = simulate_liquidity(make_stock(), position_cr=1.0)
        large = simulate_liquidity(make_stock(), position_cr=100.0)
        assert large.days_to_build > small.days_to_build

    def test_slippage_increases_with_position_size(self):
        small = simulate_liquidity(make_stock(), position_cr=1.0)
        large = simulate_liquidity(make_stock(), position_cr=20.0)
        assert large.entry_slippage_pct > small.entry_slippage_pct

    def test_roundtrip_greater_than_entry(self):
        result = simulate_liquidity(make_stock(), position_cr=5.0)
        assert result.roundtrip_slippage_pct > result.entry_slippage_pct

    def test_recommended_position_keeps_slippage_low(self):
        """Back-solved cap: if spread < 0.5%, slippage at recommended size ≈ 0.5%."""
        # Very liquid stock, low ATR so spread << 0.5%
        # Price=1000, Vol=2M → ADVT=200 Cr; ATR=5 → spread=0.125%
        stock = {"Symbol": "BIG", "Price": 1000, "Avg_Volume_10D": 2_000_000, "ATR": 5}
        probe = simulate_liquidity(stock, position_cr=1.0)
        cap = probe.recommended_position_cr
        if cap > 0:
            result_at_cap = simulate_liquidity(stock, position_cr=cap)
            # At the recommended cap entry slippage should be ≤ 0.55% (float tolerance)
            assert result_at_cap.entry_slippage_pct <= 0.55
        else:
            # If cap is 0, spread alone exceeds 0.5% — valid edge case
            assert probe.spread_pct >= 0.50

    def test_missing_price_returns_red(self):
        result = simulate_liquidity({"Symbol": "X", "Price": 0, "Avg_Volume_10D": 1_000_000}, 1.0)
        assert result.verdict == "RED"
        assert result.risk_flag is True

    def test_missing_volume_returns_red(self):
        result = simulate_liquidity({"Symbol": "X", "Price": 100, "Avg_Volume_10D": 0}, 1.0)
        assert result.verdict == "RED"

    def test_no_atr_falls_back_gracefully(self):
        stock = {"Symbol": "NOATR", "Price": 200, "Avg_Volume_10D": 1_000_000}
        result = simulate_liquidity(stock, position_cr=2.0)
        assert result.spread_pct > 0
        assert result.entry_slippage_pct > 0

    def test_advt_calculation(self):
        # Price=200, Vol=500_000 → ADVT = 200*500_000/1e7 = 10 Cr
        result = simulate_liquidity(
            {"Symbol": "ADV", "Price": 200, "Avg_Volume_10D": 500_000}, 1.0
        )
        assert abs(result.advt_cr - 10.0) < 0.1

    def test_participation_rate(self):
        # ADVT = 100 Cr, position = 10 Cr → participation = 0.10
        result = simulate_liquidity(make_stock(price=500, avg_vol=2_000_000), position_cr=10.0)
        assert abs(result.participation_rate - 0.10) < 0.01

    def test_flags_present_for_oversized_position(self):
        illiquid = {"Symbol": "SMALL", "Price": 50, "Avg_Volume_10D": 200_000}
        result = simulate_liquidity(illiquid, position_cr=10.0)
        assert len(result.flags) > 0

    def test_no_inf_in_to_dict(self):
        """to_dict() must produce JSON-serialisable numbers (no inf/nan)."""
        import json
        stock = {"Symbol": "X", "Price": 5, "Avg_Volume_10D": 10_000}
        d = simulate_liquidity(stock, position_cr=50.0).to_dict()
        json.dumps(d)

    def test_summary_string_non_empty(self):
        result = simulate_liquidity(make_stock(), position_cr=2.0)
        assert isinstance(result.summary, str)
        assert len(result.summary) > 20

    def test_max_safe_gt_recommended(self):
        result = simulate_liquidity(make_stock(), position_cr=1.0)
        assert result.max_safe_position_cr >= result.recommended_position_cr

    @pytest.mark.parametrize("pos_cr", [0.1, 1.0, 5.0, 25.0, 100.0])
    def test_various_position_sizes_dont_crash(self, pos_cr):
        result = simulate_liquidity(make_stock(), position_cr=pos_cr)
        assert result.verdict in ("GREEN", "AMBER", "RED")

    @pytest.mark.parametrize("price,vol", [
        (5, 10_000),        # micro-cap penny
        (100, 100_000),     # small-cap
        (500, 1_000_000),   # mid-cap
        (3000, 5_000_000),  # large-cap
    ])
    def test_various_market_caps_dont_crash(self, price, vol):
        stock = {"Symbol": "X", "Price": price, "Avg_Volume_10D": vol}
        result = simulate_liquidity(stock, position_cr=5.0)
        assert math.isfinite(result.advt_cr)
        assert math.isfinite(result.entry_slippage_pct)

    def test_impact_only_verdict_logic(self):
        """Verdict is GREEN when impact-only component (ex spread) is tiny."""
        # Very low ATR → spread is tiny; position is small relative to ADVT
        stock = {"Symbol": "LIQ", "Price": 2000, "Avg_Volume_10D": 5_000_000, "ATR": 10}
        # ADVT = 2000*5M/1e7 = 1000 Cr; spread = (10/2000)*100*0.25 = 0.125%
        result = simulate_liquidity(stock, position_cr=1.0)
        assert result.verdict == "GREEN"

    def test_spread_pct_capped_at_5_percent(self):
        """Spread proxy must not exceed 5% even for extremely illiquid stocks."""
        stock = {"Symbol": "ILLIQ2", "Price": 1, "Avg_Volume_10D": 100, "ATR": 2}
        result = simulate_liquidity(stock, position_cr=0.01)
        assert result.spread_pct <= 5.0
