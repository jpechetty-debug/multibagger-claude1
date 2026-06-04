"""Tests for the component-based Indian equity transaction cost model.

Covers:
  compute_round_trip_cost():
    - correct formula: all components sum correctly
    - cap category routing (Large / Mid / Small)
    - adv_30d explicit override
    - zero / negative adv_30d falls back to cap-category estimate
    - non-finite trade_value → zero impact
    - total cost ordering: large < mid < small
    - env var overrides via monkeypatch

  cost_breakdown():
    - returns all required keys
    - total_round_trip matches compute_round_trip_cost()
    - values are non-negative finite floats

  apply_transaction_costs():
    - backward-compat: explicit transaction_cost still works
    - component model used when transaction_cost=None
    - cap_category flows through
    - zero turnover → no cost deducted
    - full turnover (1.0) deducts exactly one round-trip cost
    - turnover clipped to [0, 1]
    - NaN in gross_returns propagated correctly
    - series and scalar turnover both work

  2025 rate validation:
    - large cap round-trip < 0.30% (competitive benchmark)
    - mid cap round-trip < 0.50%
    - small cap round-trip < 1.00%
    - component rates match current SEBI/NSE schedules

  VectorBTEngine:
    - accepts cap_category in __init__
    - transaction_cost=None uses component model
    - explicit transaction_cost overrides component model
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_engine(monkeypatch):
    stubs = {
        "vectorbt": types.ModuleType("vectorbt"),
        "vectorbt.portfolio": types.ModuleType("vectorbt.portfolio"),
        "vectorbt.portfolio.base": types.ModuleType("vectorbt.portfolio.base"),
        "xgboost": types.ModuleType("xgboost"),
        "sklearn": types.ModuleType("sklearn"),
        "sklearn.preprocessing": types.ModuleType("sklearn.preprocessing"),
        "sklearn.model_selection": types.ModuleType("sklearn.model_selection"),
    }
    stubs["sklearn.preprocessing"].StandardScaler = object  # type: ignore
    stubs["sklearn.model_selection"].TimeSeriesSplit = object  # type: ignore
    stubs["xgboost"].XGBRegressor = object  # type: ignore
    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)
    sys.modules.pop("backtest.backtest_engine", None)
    return importlib.import_module("backtest.backtest_engine")


# ── compute_round_trip_cost ───────────────────────────────────────────────────

class TestComputeRoundTripCost:

    def test_correct_formula_large_cap(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        import config
        # Manually compute expected value
        adv_frac = config.TC_ADV_FRAC_LARGE
        gst = config.TC_BROKERAGE_PER_SIDE * config.TC_GST_RATE
        buy = (
            config.TC_BROKERAGE_PER_SIDE
            + gst
            + config.TC_STAMP_BUY
            + config.TC_EXCHANGE
            + config.TC_SEBI_FEE
        )
        sell = (
            config.TC_BROKERAGE_PER_SIDE
            + gst
            + config.TC_STT_SELL
            + config.TC_EXCHANGE
            + config.TC_SEBI_FEE
        )
        impact = config.TC_IMPACT_ALPHA / (adv_frac ** 0.5)
        expected = buy + sell + 2 * impact

        result = mod.compute_round_trip_cost("Large")
        assert result == pytest.approx(expected, rel=1e-9)

    def test_correct_formula_mid_cap(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        import config
        adv_frac = config.TC_ADV_FRAC_MID
        gst = config.TC_BROKERAGE_PER_SIDE * config.TC_GST_RATE
        buy = (
            config.TC_BROKERAGE_PER_SIDE
            + gst
            + config.TC_STAMP_BUY
            + config.TC_EXCHANGE
            + config.TC_SEBI_FEE
        )
        sell = (
            config.TC_BROKERAGE_PER_SIDE
            + gst
            + config.TC_STT_SELL
            + config.TC_EXCHANGE
            + config.TC_SEBI_FEE
        )
        impact = config.TC_IMPACT_ALPHA / (adv_frac ** 0.5)
        expected = buy + sell + 2 * impact

        result = mod.compute_round_trip_cost("Mid")
        assert result == pytest.approx(expected, rel=1e-9)

    def test_correct_formula_small_cap(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        import config
        adv_frac = config.TC_ADV_FRAC_SMALL
        gst = config.TC_BROKERAGE_PER_SIDE * config.TC_GST_RATE
        buy = (
            config.TC_BROKERAGE_PER_SIDE
            + gst
            + config.TC_STAMP_BUY
            + config.TC_EXCHANGE
            + config.TC_SEBI_FEE
        )
        sell = (
            config.TC_BROKERAGE_PER_SIDE
            + gst
            + config.TC_STT_SELL
            + config.TC_EXCHANGE
            + config.TC_SEBI_FEE
        )
        impact = config.TC_IMPACT_ALPHA / (adv_frac ** 0.5)
        expected = buy + sell + 2 * impact

        result = mod.compute_round_trip_cost("Small")
        assert result == pytest.approx(expected, rel=1e-9)

    def test_cost_ordering_large_lt_mid_lt_small(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        large = mod.compute_round_trip_cost("Large")
        mid   = mod.compute_round_trip_cost("Mid")
        small = mod.compute_round_trip_cost("Small")
        assert large < mid < small, (
            f"Expected large({large:.5f}) < mid({mid:.5f}) < small({small:.5f})"
        )

    def test_explicit_adv_30d_overrides_cap_category(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        import config
        # With a very large ADV → near-zero impact
        high_adv = mod.compute_round_trip_cost("Small", trade_value=1.0, adv_30d=1e9)
        # With cap-based (small) → higher impact
        cap_based = mod.compute_round_trip_cost("Small")
        assert high_adv < cap_based, "Explicit high ADV should give lower cost than cap estimate"

    def test_zero_adv_falls_back_to_cap(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        zero_adv = mod.compute_round_trip_cost("Mid", adv_30d=0)
        cap_based = mod.compute_round_trip_cost("Mid")
        assert zero_adv == pytest.approx(cap_based, rel=1e-9)

    def test_negative_adv_falls_back_to_cap(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        neg_adv = mod.compute_round_trip_cost("Mid", adv_30d=-100)
        cap_based = mod.compute_round_trip_cost("Mid")
        assert neg_adv == pytest.approx(cap_based, rel=1e-9)

    def test_non_finite_trade_value_gives_zero_impact(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        import config
        # With infinite trade_value → impact should be 0 (guard)
        result = mod.compute_round_trip_cost("Mid", trade_value=float("inf"), adv_30d=1e6)
        gst = config.TC_BROKERAGE_PER_SIDE * config.TC_GST_RATE
        base = (
            config.TC_BROKERAGE_PER_SIDE + gst + config.TC_STAMP_BUY
            + config.TC_EXCHANGE + config.TC_SEBI_FEE
            + config.TC_BROKERAGE_PER_SIDE + gst + config.TC_STT_SELL
            + config.TC_EXCHANGE + config.TC_SEBI_FEE
        )
        assert result == pytest.approx(base, rel=1e-9)

    def test_market_impact_formula_matches_spec(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        import config
        trade_value = 10_000_000
        adv = 1_000_000_000
        result = mod.compute_round_trip_cost("Mid", trade_value=trade_value, adv_30d=adv)
        base_only = mod.compute_round_trip_cost("Mid", trade_value=float("inf"), adv_30d=adv)
        expected_impact_round_trip = 2 * config.TC_IMPACT_ALPHA * ((trade_value / adv) ** 0.5)
        assert result - base_only == pytest.approx(expected_impact_round_trip, rel=1e-9)

    def test_case_insensitive_cap_category(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        assert mod.compute_round_trip_cost("large") == mod.compute_round_trip_cost("Large")
        assert mod.compute_round_trip_cost("SMALL") == mod.compute_round_trip_cost("Small")
        assert mod.compute_round_trip_cost("MID")   == mod.compute_round_trip_cost("Mid")

    def test_unknown_cap_defaults_to_mid(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        unknown = mod.compute_round_trip_cost("Unknown")
        mid     = mod.compute_round_trip_cost("Mid")
        assert unknown == pytest.approx(mid, rel=1e-9)

    def test_result_is_finite_positive(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        for cap in ["Large", "Mid", "Small"]:
            result = mod.compute_round_trip_cost(cap)
            assert np.isfinite(result) and result > 0, f"Bad result for {cap}: {result}"


# ── 2025 rate sanity bounds ───────────────────────────────────────────────────

class Test2025RateBounds:
    """Validate computed costs are in line with actual Indian market rates."""

    def test_large_cap_under_30bps(self, monkeypatch):
        """Large cap round-trip should be < 0.30% (30bps) for well-traded stocks."""
        mod = _load_engine(monkeypatch)
        assert mod.compute_round_trip_cost("Large") < 0.003

    def test_mid_cap_under_50bps(self, monkeypatch):
        """Mid cap round-trip < 0.50% (50bps)."""
        mod = _load_engine(monkeypatch)
        assert mod.compute_round_trip_cost("Mid") < 0.005

    def test_small_cap_under_100bps(self, monkeypatch):
        """Small cap round-trip < 1.00% (100bps)."""
        mod = _load_engine(monkeypatch)
        assert mod.compute_round_trip_cost("Small") < 0.01

    def test_stt_rate_is_01_percent(self):
        """STT on sell delivery must be 0.1% per Finance Act 2004."""
        import config
        assert config.TC_STT_SELL == pytest.approx(0.001, rel=1e-6)

    def test_stamp_duty_is_015_percent(self):
        """Stamp duty on buy must be 0.015% per State Stamp Act 2020."""
        import config
        assert config.TC_STAMP_BUY == pytest.approx(0.00015, rel=1e-6)

    def test_component_costs_are_env_overridable(self, monkeypatch):
        """All TC_ constants must read from environment variables."""
        import config
        # Verify they read from env by checking they use os.getenv
        import inspect
        src = inspect.getsource(config)
        for var in ["TC_STT_SELL", "TC_EXCHANGE", "TC_SEBI_FEE",
                    "TC_STAMP_BUY", "TC_BROKERAGE_PER_SIDE",
                    "TC_GST_RATE", "TC_IMPACT_ALPHA"]:
            assert f'os.getenv("{var}"' in src, \
                f"{var} is not env-overridable in config.py"

    def test_old_flat_constant_preserved(self):
        """TRANSACTION_COST still importable for backward-compat."""
        import config
        assert hasattr(config, "TRANSACTION_COST")
        assert isinstance(config.TRANSACTION_COST, float)


# ── cost_breakdown ────────────────────────────────────────────────────────────

class TestCostBreakdown:

    REQUIRED_KEYS = {
        "brokerage_per_side", "gst_on_brokerage_per_side", "stt_sell",
        "exchange_per_side", "sebi_fee_per_side", "stamp_duty_buy",
        "impact_per_way", "total_round_trip",
    }

    def test_all_keys_present(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        bd = mod.cost_breakdown("Mid")
        assert self.REQUIRED_KEYS == set(bd.keys())

    def test_total_matches_compute_round_trip_cost(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        for cap in ["Large", "Mid", "Small"]:
            bd = mod.cost_breakdown(cap)
            expected = mod.compute_round_trip_cost(cap)
            assert bd["total_round_trip"] == pytest.approx(expected, rel=1e-6), \
                f"cost_breakdown total mismatch for {cap}"

    def test_all_values_non_negative_finite(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        for cap in ["Large", "Mid", "Small"]:
            for key, val in mod.cost_breakdown(cap).items():
                assert np.isfinite(val) and val >= 0, f"{cap}[{key}] = {val}"

    def test_stt_matches_config(self, monkeypatch):
        import config
        mod = _load_engine(monkeypatch)
        bd = mod.cost_breakdown("Mid")
        assert bd["stt_sell"] == pytest.approx(config.TC_STT_SELL, rel=1e-9)


# ── apply_transaction_costs ───────────────────────────────────────────────────

class TestApplyTransactionCosts:

    def test_zero_turnover_no_deduction(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05, 0.03, -0.02, 0.04])
        net = mod.apply_transaction_costs(gross, turnover=0.0)
        pd.testing.assert_series_equal(net, gross)

    def test_full_turnover_deducts_one_round_trip(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05, 0.03, 0.04])
        net = mod.apply_transaction_costs(gross, turnover=1.0, cap_category="Mid")
        cost = mod.compute_round_trip_cost("Mid")
        expected = gross - cost
        pd.testing.assert_series_equal(net, expected)

    def test_turnover_over_1_clipped_to_1(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05])
        net_100pct = mod.apply_transaction_costs(gross, turnover=1.0, cap_category="Mid")
        net_200pct = mod.apply_transaction_costs(gross, turnover=2.0, cap_category="Mid")
        # Turnover > 1 should be clipped — cost same as 100% turnover
        pd.testing.assert_series_equal(net_100pct, net_200pct)

    def test_explicit_transaction_cost_overrides_component(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05, 0.03])
        net_explicit = mod.apply_transaction_costs(gross, turnover=1.0, transaction_cost=0.001)
        expected = gross - 0.001
        pd.testing.assert_series_equal(net_explicit, expected)

    def test_none_transaction_cost_uses_component_model(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05, 0.03])
        net_none = mod.apply_transaction_costs(
            gross, turnover=1.0, transaction_cost=None, cap_category="Large"
        )
        cost = mod.compute_round_trip_cost("Large")
        expected = gross - cost
        pd.testing.assert_series_equal(net_none, expected)

    def test_cap_category_changes_cost(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.10])
        net_large = mod.apply_transaction_costs(gross, turnover=1.0,
                                                transaction_cost=None, cap_category="Large")
        net_small = mod.apply_transaction_costs(gross, turnover=1.0,
                                                transaction_cost=None, cap_category="Small")
        assert net_large.iloc[0] > net_small.iloc[0], \
            "Large cap should have lower cost → higher net return"

    def test_series_turnover_applied_per_period(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05, 0.03, 0.04])
        turnover = pd.Series([0.0, 1.0, 0.5])
        net = mod.apply_transaction_costs(gross, turnover, cap_category="Mid")
        cost = mod.compute_round_trip_cost("Mid")
        expected = pd.Series([
            0.05 - 0.0 * cost,
            0.03 - 1.0 * cost,
            0.04 - 0.5 * cost,
        ])
        pd.testing.assert_series_equal(net, expected)

    def test_nan_in_gross_propagates(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05, float("nan"), 0.04])
        net = mod.apply_transaction_costs(gross, turnover=0.5, cap_category="Mid")
        assert np.isnan(net.iloc[1])

    def test_backward_compat_positional_arg(self, monkeypatch):
        """Legacy callers pass transaction_cost as 3rd positional arg."""
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.05, 0.03])
        # Positional: apply_transaction_costs(gross, turnover, transaction_cost)
        net = mod.apply_transaction_costs(gross, 1.0, 0.003)
        expected = gross - 0.003
        pd.testing.assert_series_equal(net, expected)


# ── VectorBTEngine integration ────────────────────────────────────────────────

class TestVectorBTEngineCapCategory:

    def test_init_accepts_cap_category(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        engine = mod.VectorBTEngine(cap_category="Small")
        assert engine.cap_category == "Small"

    def test_default_cap_category_is_mid(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        engine = mod.VectorBTEngine()
        assert engine.cap_category == "Mid"

    def test_none_transaction_cost_default(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        engine = mod.VectorBTEngine()
        assert engine.transaction_cost is None

    def test_explicit_transaction_cost_stored(self, monkeypatch):
        mod = _load_engine(monkeypatch)
        engine = mod.VectorBTEngine(transaction_cost=0.004)
        assert engine.transaction_cost == pytest.approx(0.004)

    def test_large_vs_small_produces_different_net_returns(self, monkeypatch):
        """Same gross return, different cap category → different net returns."""
        mod = _load_engine(monkeypatch)
        gross = pd.Series([0.10])
        net_l = mod.apply_transaction_costs(gross, 1.0, None, "Large")
        net_s = mod.apply_transaction_costs(gross, 1.0, None, "Small")
        assert net_l.iloc[0] > net_s.iloc[0]
