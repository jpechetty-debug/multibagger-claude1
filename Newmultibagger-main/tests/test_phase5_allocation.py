"""Tests for Phase 5: Regime-Aware Allocation Adjustment.

Covers:
  - Module 5.1: RegimeHMM caching and state mapping.
  - Module 5.2: PortfolioOptimizer dynamic limit adjustments based on regime.
  - Module 5.3: YieldRedirectController cash sweep and yield calculations.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.risk.regime_hmm import RegimeHMM
from modules.portfolio.optimizer import PortfolioOptimizer
from modules.portfolio.capital_efficiency import YieldRedirectController


# ── Module 5.1: Hidden Markov Model Classifier ─────────────────────────────

class TestRegimeHMM:
    
    @patch("modules.risk.regime_hmm.yf.download")
    def test_predict_regime_empty_data_fallback(self, mock_download):
        """Should return VOLATILE if no data is available."""
        mock_download.return_value = pd.DataFrame()
        
        hmm = RegimeHMM(model_path="dummy.pkl")
        regime = hmm.predict_regime()
        assert regime == "VOLATILE"

    @patch("modules.risk.regime_hmm.yf.download")
    def test_predict_regime_insufficient_returns(self, mock_download):
        """Should return VOLATILE if not enough data points (< 10)."""
        df = pd.DataFrame({"Close": [100.0, 101.0, 102.0]}) # Only 2 returns
        mock_download.return_value = df
        
        hmm = RegimeHMM(model_path="dummy.pkl")
        regime = hmm.predict_regime()
        assert regime == "VOLATILE"

    def test_map_state_to_regime(self):
        """Test mapping logic based on means sorting."""
        hmm = RegimeHMM(model_path="dummy.pkl")
        # Mock model attributes that are usually populated by hmmlearn fit()
        mock_model = MagicMock()
        mock_model.means_ = np.array([[-0.01], [0.00], [0.02]])
        mock_model.covars_ = np.array([[[0.01]], [[0.005]], [[0.001]]])
        hmm.model = mock_model
        
        # lowest mean (index 0) -> BEARISH
        assert hmm._map_state_to_regime(0) == "BEARISH"
        # middle mean (index 1) -> VOLATILE
        assert hmm._map_state_to_regime(1) == "VOLATILE"
        # highest mean (index 2) -> BULLISH
        assert hmm._map_state_to_regime(2) == "BULLISH"


# ── Module 5.2: Allocation Governor ────────────────────────────────────────

class TestAllocationGovernor:
    
    def test_optimizer_defaults_bullish(self):
        """Test default fallback to BULLISH if HMM is None."""
        optimizer = PortfolioOptimizer()
        optimizer.hmm = None # Simulate missing HMM
        
        stocks = [
            {"Symbol": "A", "Sector": "IT", "ATR": 5, "Price": 100},
            {"Symbol": "B", "Sector": "IT", "ATR": 10, "Price": 100}
        ]
        
        optimizer.optimize_allocation(stocks)
        # Should retain default constraints (Bullish)
        assert optimizer.max_single_weight == 0.10
        assert optimizer.max_sector_weight == 0.25
        
    def test_optimizer_adapts_to_bearish(self):
        """Test optimizer dynamically changes limits if regime is BEARISH."""
        optimizer = PortfolioOptimizer()
        
        # Mock the HMM
        mock_hmm = MagicMock()
        mock_hmm.predict_regime.return_value = "BEARISH"
        optimizer.hmm = mock_hmm
        
        stocks = [
            {"Symbol": "A", "Sector": "IT", "ATR": 5, "Price": 100},
        ]
        
        optimizer.optimize_allocation(stocks)
        
        assert optimizer.regime == "BEARISH"
        assert optimizer.max_single_weight == 0.02
        assert optimizer.max_sector_weight == 0.10


# ── Module 5.3: Yield Redirect Controller ──────────────────────────────────

class TestYieldRedirectController:
    
    def test_sweep_excess_cash(self):
        yrc = YieldRedirectController()
        assert yrc.parked_cash == 0.0
        
        yrc.sweep_excess_cash(50000.0)
        assert yrc.parked_cash == 50000.0
        
        yrc.sweep_excess_cash(10000.0)
        assert yrc.parked_cash == 60000.0
        
    def test_release_cash(self):
        yrc = YieldRedirectController()
        yrc.sweep_excess_cash(50000.0)
        
        released = yrc.release_cash(20000.0)
        assert released == 20000.0
        assert yrc.parked_cash == 30000.0
        
        # Try to release more than parked
        released = yrc.release_cash(50000.0)
        assert released == 30000.0 # Can only release what's left
        assert yrc.parked_cash == 0.0
        
    def test_calculate_yield(self):
        yrc = YieldRedirectController()
        yrc.sweep_excess_cash(100000.0) # 1 Lakh
        
        # 365 days @ 6.5% should be exactly 6500
        yield_earned = yrc.calculate_yield(365)
        assert yield_earned == pytest.approx(6500.0)
        
        # 30 days should be proportional
        yield_30d = yrc.calculate_yield(30)
        assert yield_30d == pytest.approx(100000 * 0.065 * (30/365))
