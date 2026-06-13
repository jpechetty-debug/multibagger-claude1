"""Tests for Phase 6.3: Friction Replay Simulator."""

import pytest
import numpy as np

import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.liquidity_filter import LiquidityFilter
from backtest.backtest_engine import compute_round_trip_cost

def test_liquidity_filter():
    """Verify that LiquidityFilter correctly screens out illiquid stocks."""
    filter = LiquidityFilter(min_price=10.0, min_turnover=5_000_000)
    
    universe = [
        {"Symbol": "A", "Price": 5.0, "Volume": 1000000},  # Price too low
        {"Symbol": "B", "Price": 100.0, "Volume": 10000},  # Turnover = 1,000,000 (too low)
        {"Symbol": "C", "Price": 50.0, "Volume": 200000},  # Turnover = 10,000,000 (Passes)
    ]
    
    filtered = filter.filter(universe)
    assert len(filtered) == 1
    assert filtered[0]["Symbol"] == "C"

def test_compute_round_trip_cost_dynamic_impact():
    """Verify that round-trip cost incorporates dynamic market impact."""
    
    # Base case: small trade, no explicit ADV -> falls back to base impact calculation
    cost_base = compute_round_trip_cost(cap_category="Mid")
    assert cost_base > 0
    
    # Large trade relative to ADV -> higher impact
    cost_large_trade = compute_round_trip_cost(
        cap_category="Mid",
        trade_value=1_000_000,  # 10 Lakhs
        adv_30d=5_000_000       # 50 Lakhs ADV
    )
    
    # Small trade relative to ADV -> lower impact
    cost_small_trade = compute_round_trip_cost(
        cap_category="Mid",
        trade_value=100_000,    # 1 Lakh
        adv_30d=5_000_000       # 50 Lakhs ADV
    )
    
    assert cost_large_trade > cost_small_trade
    
def test_compute_round_trip_cost_zero_trade():
    """Verify graceful handling of zero/invalid trade values."""
    cost = compute_round_trip_cost(
        cap_category="Mid",
        trade_value=0,
        adv_30d=5_000_000
    )
    # With zero trade, impact is zero, only base cost remains
    assert cost > 0
    
    cost_neg = compute_round_trip_cost(
        cap_category="Mid",
        trade_value=-1000,
        adv_30d=5_000_000
    )
    assert cost_neg == cost # same base cost, impact is zero
