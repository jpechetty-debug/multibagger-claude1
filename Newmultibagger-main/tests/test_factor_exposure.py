"""Tests for factor_exposure module."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.factor_exposure import check_factor_alerts, compute_factor_betas


def test_beta_computation_correlated():
    rng = np.random.RandomState(0)
    market = pd.Series(rng.randn(60) * 0.02)
    port = market * 1.2 + rng.randn(60) * 0.001  # beta ≈ 1.2
    betas = compute_factor_betas(port, {"market": market})
    assert abs(betas["market"]["beta"] - 1.2) < 0.15
    assert betas["market"]["r2"] > 0.8


def test_beta_uncorrelated():
    rng = np.random.RandomState(1)
    port = pd.Series(rng.randn(60))
    factor = pd.Series(rng.randn(60))
    betas = compute_factor_betas(port, {"noise": factor})
    assert abs(betas["noise"]["beta"]) < 0.5


def test_momentum_alert():
    betas = {"momentum_factor": {"beta": 0.7, "t_stat": 3.0, "r2": 0.4}}
    alerts = check_factor_alerts(betas)
    assert any("MOMENTUM_OVERLOAD" in a for a in alerts)


def test_size_alert():
    betas = {"size_factor": {"beta": -0.5, "t_stat": -2.0, "r2": 0.2}}
    alerts = check_factor_alerts(betas)
    assert any("SIZE_TILT" in a for a in alerts)


def test_no_alert_within_bounds():
    betas = {
        "momentum_factor": {"beta": 0.3, "t_stat": 1.5, "r2": 0.1},
        "size_factor": {"beta": 0.1, "t_stat": 0.5, "r2": 0.05},
    }
    alerts = check_factor_alerts(betas)
    assert len(alerts) == 0
