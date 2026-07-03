"""Tests for ic_monitor module."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.ic_monitor import compute_ic_by_regime


def test_perfect_correlation_high_ic():
    n = 30
    df = pd.DataFrame({
        "prediction": np.arange(n, dtype=float),
        "forward_return": np.arange(n, dtype=float) * 0.01,
    })
    regimes = pd.Series(["BULL"] * n, index=df.index)
    result = compute_ic_by_regime(df, regimes)
    assert result["BULL"]["confidence"] == "HIGH"
    assert result["BULL"]["ic"] == pytest.approx(1.0)


def test_random_predictions_low_confidence():
    rng = np.random.RandomState(99)
    n = 50
    df = pd.DataFrame({
        "prediction": rng.randn(n),
        "forward_return": rng.randn(n),
    })
    regimes = pd.Series(["BEAR"] * n, index=df.index)
    result = compute_ic_by_regime(df, regimes)
    assert result["BEAR"]["confidence"] == "LOW_SIGNAL_CONFIDENCE"


def test_multiple_regimes():
    rng = np.random.RandomState(7)
    n = 60
    preds = rng.randn(n)
    actuals = rng.randn(n)
    # Make BULL highly correlated
    actuals[:20] = preds[:20] * 0.5 + rng.randn(20) * 0.01
    df = pd.DataFrame({"prediction": preds, "forward_return": actuals})
    regimes = pd.Series(
        ["BULL"] * 20 + ["BEAR"] * 20 + ["SIDEWAYS"] * 20,
        index=df.index,
    )
    result = compute_ic_by_regime(df, regimes)
    assert "BULL" in result
    assert "BEAR" in result
    assert result["BULL"]["ic"] > result["BEAR"]["ic"]


def test_insufficient_data():
    df = pd.DataFrame({"prediction": [1.0, 2.0], "forward_return": [0.01, 0.02]})
    regimes = pd.Series(["BULL", "BULL"], index=df.index)
    result = compute_ic_by_regime(df, regimes)
    assert result["BULL"]["confidence"] == "INSUFFICIENT_DATA"
