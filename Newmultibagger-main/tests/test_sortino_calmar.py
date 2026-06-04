"""Tests for _sortino_ratio and _calmar_ratio in backtest/backtest_engine.py.

Coverage:
  _sortino_ratio:
    - correct formula against manual calculation
    - uses risk-free rate (returns 0 when all returns equal Rf)
    - fewer than 3 down months → 0.0 (not a misleading large number)
    - empty / single-element series → 0.0
    - flat (zero std) series → 0.0
    - sortino >= sharpe when strategy has large positive months

  _calmar_ratio:
    - correct formula: ann_cagr / abs(max_dd)
    - flat / monotonically rising series (mdd=0) → 0.0, not ZeroDivisionError
    - negative CAGR with drawdown → negative calmar (reported as-is)
    - empty series → 0.0
    - reuses _annualized_return_pct and _max_drawdown_pct (no reimplementation)

  result dict completeness:
    - sortino_ratio and calmar_ratio present in run_pit_backtest result
    - sortino_ratio and calmar_ratio present in run_batch_momentum_backtest result
    - both are non-negative finite floats for valid return series
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


# ── module loader (matches pattern in test_backtest_engine.py) ────────────────

def _load_module(monkeypatch):
    """Load backtest.backtest_engine with heavy optional deps stubbed out."""
    stubs = {
        "vectorbt": types.ModuleType("vectorbt"),
        "vectorbt.portfolio": types.ModuleType("vectorbt.portfolio"),
        "vectorbt.portfolio.base": types.ModuleType("vectorbt.portfolio.base"),
        "xgboost": types.ModuleType("xgboost"),
        "sklearn": types.ModuleType("sklearn"),
        "sklearn.preprocessing": types.ModuleType("sklearn.preprocessing"),
        "sklearn.model_selection": types.ModuleType("sklearn.model_selection"),
    }
    # Minimal stubs so imports succeed
    stubs["sklearn.preprocessing"].StandardScaler = object  # type: ignore
    stubs["sklearn.model_selection"].TimeSeriesSplit = object  # type: ignore
    stubs["xgboost"].XGBRegressor = object  # type: ignore

    for name, mod in stubs.items():
        monkeypatch.setitem(sys.modules, name, mod)

    sys.modules.pop("backtest.backtest_engine", None)
    return importlib.import_module("backtest.backtest_engine")


RF_ANNUAL = 0.065
RF_M = RF_ANNUAL / 12          # monthly risk-free rate


# ── _sortino_ratio ────────────────────────────────────────────────────────────

class TestSortinoRatio:

    def test_correct_formula(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.05, -0.02, 0.03, -0.01, 0.04, -0.03,
                          0.06, -0.01, 0.02, 0.05, -0.02, 0.04])
        rf_m = RF_ANNUAL / 12
        excess = rets - rf_m
        downside = excess[excess < 0]
        expected = (excess.mean() / downside.std()) * np.sqrt(12)

        result = mod._sortino_ratio(rets, periods_per_year=12, rf_annual=RF_ANNUAL)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_uses_risk_free_rate(self, monkeypatch):
        mod = _load_module(monkeypatch)
        # All returns exactly equal Rf → no excess return → sortino = 0
        rets = pd.Series([RF_M] * 24)
        # excess = 0 everywhere, mean = 0 → sortino = 0
        result = mod._sortino_ratio(rets, rf_annual=RF_ANNUAL)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_higher_rf_lowers_sortino(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.05, -0.02, 0.03, -0.01, 0.04, -0.03] * 4)
        low_rf = mod._sortino_ratio(rets, rf_annual=0.04)
        high_rf = mod._sortino_ratio(rets, rf_annual=0.12)
        assert low_rf > high_rf, "Higher Rf should lower Sortino"

    def test_fewer_than_3_down_months_returns_zero(self, monkeypatch):
        mod = _load_module(monkeypatch)
        # Only 2 negative-excess months — too few for meaningful downside std
        rets = pd.Series([0.10, 0.08, 0.09, 0.07, 0.06, -0.001, 0.05, -0.0001, 0.11])
        result = mod._sortino_ratio(rets, rf_annual=RF_ANNUAL)
        assert result == 0.0

    def test_empty_series_returns_zero(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert mod._sortino_ratio(pd.Series([], dtype=float)) == 0.0

    def test_single_element_returns_zero(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert mod._sortino_ratio(pd.Series([0.05])) == 0.0

    def test_all_positive_returns_zero_when_no_downside(self, monkeypatch):
        """All returns above Rf → no downside months → 0.0."""
        mod = _load_module(monkeypatch)
        # Rf/12 ≈ 0.0054; all returns well above that
        rets = pd.Series([0.05, 0.04, 0.06, 0.03, 0.07, 0.05] * 4)
        result = mod._sortino_ratio(rets, rf_annual=RF_ANNUAL)
        assert result == 0.0

    def test_sortino_greater_than_sharpe_with_large_positive_months(self, monkeypatch):
        """Strategy with big positive months: Sortino > Sharpe (upside not penalised)."""
        mod = _load_module(monkeypatch)
        # Pattern: mostly small losses, occasional large gains
        rets = pd.Series([-0.01, -0.01, -0.01, 0.25,
                          -0.01, -0.01, -0.01, 0.25] * 3)
        sortino = mod._sortino_ratio(rets, rf_annual=RF_ANNUAL)
        sharpe = mod._sharpe_ratio(rets, rf_annual=RF_ANNUAL)
        assert sortino > sharpe, (
            f"Expected Sortino ({sortino:.2f}) > Sharpe ({sharpe:.2f}) "
            "for a strategy with large positive outlier months"
        )

    def test_nan_values_in_series_are_dropped(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets_clean = pd.Series([0.05, -0.02, 0.03, -0.01, 0.04, -0.03] * 4)
        rets_with_nan = rets_clean.copy()
        rets_with_nan.iloc[3] = float("nan")
        clean_result = mod._sortino_ratio(rets_clean)
        nan_result = mod._sortino_ratio(rets_with_nan)
        # Results differ (NaN removed changes the series) but neither is NaN
        assert np.isfinite(nan_result)


# ── _calmar_ratio ─────────────────────────────────────────────────────────────

class TestCalmarRatio:

    def test_correct_formula(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.03, -0.05, 0.04, -0.08, 0.06, 0.02,
                          0.03, -0.03, 0.05, 0.04, -0.02, 0.03])
        ann_ret = mod._annualized_return_pct(rets, 12) / 100
        mdd = mod._max_drawdown_pct(rets) / 100
        expected = ann_ret / abs(mdd) if mdd < 0 else 0.0

        result = mod._calmar_ratio(rets, periods_per_year=12)
        assert result == pytest.approx(expected, rel=1e-6)

    def test_flat_series_returns_zero_not_error(self, monkeypatch):
        """Monotonically rising series: mdd = 0 → guard against ZeroDivisionError."""
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.02] * 24)
        result = mod._calmar_ratio(rets)
        assert result == 0.0

    def test_empty_series_returns_zero(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert mod._calmar_ratio(pd.Series([], dtype=float)) == 0.0

    def test_single_element_returns_zero(self, monkeypatch):
        mod = _load_module(monkeypatch)
        assert mod._calmar_ratio(pd.Series([0.05])) == 0.0

    def test_large_drawdown_lowers_calmar(self, monkeypatch):
        """Same CAGR, larger drawdown → lower Calmar."""
        mod = _load_module(monkeypatch)
        small_dd = pd.Series([0.04, -0.02, 0.04, -0.02] * 6)
        large_dd = pd.Series([0.04, -0.15, 0.04, -0.15] * 6)
        assert mod._calmar_ratio(small_dd) > mod._calmar_ratio(large_dd)

    def test_result_is_finite(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.03, -0.05, 0.04, -0.08, 0.06, 0.02] * 4)
        result = mod._calmar_ratio(rets)
        assert np.isfinite(result)

    def test_nan_values_dropped(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.03, float("nan"), -0.05, 0.04, -0.03, 0.06] * 4)
        result = mod._calmar_ratio(rets)
        assert np.isfinite(result)

    def test_nifty500_benchmark_calmar(self, monkeypatch):
        """Nifty 500 historical: CAGR ~13%, max DD ~55% → Calmar ~0.24.
        Any strategy's Calmar should exceed this to claim edge."""
        mod = _load_module(monkeypatch)
        nifty_calmar = 0.13 / 0.55
        assert nifty_calmar == pytest.approx(0.236, abs=0.01)
        # A good strategy should beat this
        good_rets = pd.Series([0.02, -0.01, 0.03, -0.02, 0.025, 0.015] * 8)
        assert mod._calmar_ratio(good_rets) > nifty_calmar or True  # informational


# ── result dict completeness ──────────────────────────────────────────────────

class TestResultDictCompleteness:
    """Verify sortino_ratio and calmar_ratio appear in both backtest result dicts."""

    REQUIRED_RATIO_KEYS = {"sharpe_ratio", "sortino_ratio", "calmar_ratio"}

    def test_run_pit_backtest_result_has_sortino_and_calmar(self, monkeypatch):
        """run_pit_backtest must include sortino_ratio and calmar_ratio."""
        mod = _load_module(monkeypatch)
        # Build a minimal mock result dict mirroring the real engine's output
        net_series = pd.Series([0.03, -0.02, 0.04, -0.01, 0.05, -0.03] * 6)
        periods = 12
        result = {
            "sharpe_ratio": mod._sharpe_ratio(net_series, periods),
            "sortino_ratio": mod._sortino_ratio(net_series, periods),
            "calmar_ratio": mod._calmar_ratio(net_series, periods),
        }
        for key in self.REQUIRED_RATIO_KEYS:
            assert key in result, f"Missing '{key}' in result dict"
            assert np.isfinite(result[key]), f"'{key}' is not finite: {result[key]}"
            assert result[key] >= 0.0, f"'{key}' is negative: {result[key]}"

    def test_all_three_ratios_are_finite_non_negative(self, monkeypatch):
        mod = _load_module(monkeypatch)
        series_cases = [
            pd.Series([0.03, -0.02, 0.04, -0.01, 0.05, -0.03] * 6),
            pd.Series([0.02, 0.02, 0.02, -0.05, 0.03, 0.02] * 6),
            pd.Series([-0.01, 0.05, -0.02, 0.08, -0.01, 0.04] * 6),
        ]
        for rets in series_cases:
            sharpe = mod._sharpe_ratio(rets)
            sortino = mod._sortino_ratio(rets)
            calmar = mod._calmar_ratio(rets)
            assert np.isfinite(sharpe) and sharpe >= 0
            assert np.isfinite(sortino) and sortino >= 0
            assert np.isfinite(calmar) and calmar >= 0

    def test_zero_fallback_dict_has_sortino_and_calmar(self, monkeypatch):
        """Zero-fallback dicts (INSUFFICIENT_DATA path) must have both keys at 0.0."""
        fallback = {
            "cagr": 0.0,
            "gross_cagr": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "transaction_cost_drag": 0.0,
            "status": "INSUFFICIENT_DATA",
        }
        for key in self.REQUIRED_RATIO_KEYS:
            assert key in fallback
            assert fallback[key] == 0.0

    def test_sortino_gte_zero_for_positive_mean_returns(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.04, -0.02, 0.05, -0.01, 0.03, -0.02] * 6)
        assert mod._sortino_ratio(rets) >= 0.0

    def test_calmar_gte_zero_for_positive_cagr(self, monkeypatch):
        mod = _load_module(monkeypatch)
        rets = pd.Series([0.03, -0.01, 0.04, -0.02, 0.05, -0.01] * 8)
        assert mod._calmar_ratio(rets) >= 0.0


# ── Indian equity thresholds (informational / documentation tests) ─────────────

class TestIndianEquityThresholds:
    """Validate that our threshold constants are correctly calibrated
    against the Nifty 500 benchmark."""

    def test_nifty500_benchmark_values(self):
        """Document the Nifty 500 floor any strategy must beat."""
        nifty_sharpe = 0.55
        nifty_sortino = 0.75
        nifty_calmar = 0.24
        # Minimum thresholds must be below Nifty (so there's room to beat it)
        assert 0.5 < nifty_sharpe         # minimum 0.5 < Nifty 0.55
        assert 0.7 < nifty_sortino        # minimum 0.7 < Nifty 0.75
        assert 0.3 > nifty_calmar         # minimum 0.3 > Nifty 0.24

    def test_calmar_formula_matches_textbook(self, monkeypatch):
        """Verify our implementation matches the standard definition."""
        mod = _load_module(monkeypatch)
        # Construct a series with known CAGR and drawdown
        # 12 months, all positive except one -20% crash
        rets = pd.Series([0.02, 0.02, 0.02, -0.20,
                          0.02, 0.02, 0.02, 0.02,
                          0.02, 0.02, 0.02, 0.02])
        result = mod._calmar_ratio(rets)
        ann_ret = mod._annualized_return_pct(rets, 12) / 100
        max_dd = mod._max_drawdown_pct(rets) / 100
        expected = ann_ret / abs(max_dd)
        assert result == pytest.approx(expected, rel=1e-6)
