# tests/test_sharpe_risk_free.py
"""
Phase 1 Fix: Verify that Sharpe ratio computation properly subtracts
the risk-free rate, and that RF_ANNUAL is configurable via env var.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

plotly = pytest.importorskip("plotly", reason="plotly not installed")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestSharpeRiskFreeRate:
    """Validate Sharpe ratio subtracts rf_per_period, not zero."""

    def test_sharpe_subtracts_risk_free_per_period(self):
        from backtest.backtest_engine import _sharpe_ratio

        returns = pd.Series([0.03, 0.02, -0.01, 0.04, 0.01, 0.02])
        rf_annual = 0.065

        observed = _sharpe_ratio(returns, periods_per_year=12, rf_annual=rf_annual)

        # Manually compute expected
        rf_per_period = rf_annual / 12
        excess = returns - rf_per_period
        expected = (excess.mean() / excess.std()) * np.sqrt(12)

        assert observed == pytest.approx(expected, rel=1e-6)

    def test_sharpe_with_zero_rf_equals_information_ratio(self):
        """When RF=0, Sharpe should equal mean/std * sqrt(periods)."""
        from backtest.backtest_engine import _sharpe_ratio

        returns = pd.Series([0.03, 0.02, -0.01, 0.04])
        observed = _sharpe_ratio(returns, periods_per_year=12, rf_annual=0.0)
        expected = (returns.mean() / returns.std()) * np.sqrt(12)

        assert observed == pytest.approx(expected, rel=1e-6)

    def test_sharpe_higher_rf_produces_lower_ratio(self):
        """Higher risk-free rate should produce lower Sharpe ratio."""
        from backtest.backtest_engine import _sharpe_ratio

        returns = pd.Series([0.03, 0.02, -0.01, 0.04, 0.01])
        low_rf = _sharpe_ratio(returns, rf_annual=0.02)
        high_rf = _sharpe_ratio(returns, rf_annual=0.10)

        assert high_rf < low_rf

    def test_sharpe_default_rf_is_not_zero(self):
        """The default RF_ANNUAL must be > 0 (India G-Sec rate)."""
        from backtest.backtest_engine import RF_ANNUAL

        assert RF_ANNUAL > 0, "RF_ANNUAL must be positive for India"
        assert RF_ANNUAL >= 0.05, f"RF_ANNUAL={RF_ANNUAL} is unrealistically low for India"
        assert RF_ANNUAL <= 0.10, f"RF_ANNUAL={RF_ANNUAL} is unrealistically high"

    def test_sharpe_env_override(self, monkeypatch):
        """RF_ANNUAL should be overridable via RISK_FREE_RATE_ANNUAL env var."""
        monkeypatch.setenv("RISK_FREE_RATE_ANNUAL", "0.08")

        # Re-import to pick up env change
        import importlib

        import backtest.backtest_engine as be_module
        importlib.reload(be_module)

        assert be_module.RF_ANNUAL == pytest.approx(0.08)

        # Clean up
        monkeypatch.delenv("RISK_FREE_RATE_ANNUAL", raising=False)
        importlib.reload(be_module)

    def test_legacy_engine_uses_rf_annual(self):
        """backtest_engine_v2.py must also use RF_ANNUAL, not hardcoded 0.06."""
        from modules.backtest_engine_v2 import RF_ANNUAL

        assert RF_ANNUAL > 0
        assert RF_ANNUAL >= 0.05
