"""Tests for feature_leakage_audit module."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.feature_leakage_audit import (  # noqa: E402
    SPEARMAN_LEAK_THRESHOLD,
    audit_features,
    validate_momentum_returns,
)
from modules.scoring.ml_score import FEATURES  # noqa: E402


def _make_df(n: int = 100, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    forward = rng.randn(n)
    data = {"forward_return": forward}
    for f in FEATURES:
        data[f] = rng.randn(n) * 10  # low correlation by construction
    return pd.DataFrame(data)


def test_legitimate_features_pass():
    df = _make_df()
    report = audit_features(df)
    assert not report.has_leaks


def test_synthetic_leak_detected():
    df = _make_df()
    # Inject a perfectly correlated feature
    df["score"] = df["forward_return"] * 100
    report = audit_features(df)
    verdicts_by_name = {v.feature: v for v in report.verdicts}
    v = verdicts_by_name["score"]
    # score is a fundamental feature so it gets NEEDS_REVIEW, not LEAKING
    assert v.classification in ("NEEDS_REVIEW", "LEAKING")
    assert v.spearman_r is not None
    assert abs(v.spearman_r) > SPEARMAN_LEAK_THRESHOLD


def test_momentum_feature_leak_flagged_as_leaking():
    df = _make_df()
    # Make ret_1m perfectly predict forward_return
    df["ret_1m"] = df["forward_return"] * 50
    report = audit_features(df)
    verdicts_by_name = {v.feature: v for v in report.verdicts}
    v = verdicts_by_name["ret_1m"]
    assert v.classification == "LEAKING"


def test_empty_df():
    report = audit_features(pd.DataFrame())
    assert not report.has_leaks
    assert len(report.verdicts) == 0


def test_validate_momentum_returns_catches_mismatch():
    dates = pd.date_range("2023-01-01", periods=6, freq="MS")
    prices = [100, 110, 105, 115, 120, 118]
    # ret_1m deliberately wrong
    ret_1m = [0, 50, -10, 20, 5, -2]
    df = pd.DataFrame({
        "symbol": "AAA.NS",
        "as_of_date": dates,
        "price": prices,
        "ret_1m": ret_1m,
    })
    issues = validate_momentum_returns(df, tolerance=0.01)
    assert len(issues) > 0
    assert issues[0]["symbol"] == "AAA.NS"


def test_momentum_low_correlation_safe():
    df = _make_df()  # correlation is low (< 0.15) by construction
    # Force all momentum features to 0.0 to guarantee zero correlation
    for f in ["ret_1m", "ret_3m", "ret_6m", "vol_breakout", "dist_from_52w_high"]:
        df[f] = 0.0
    report = audit_features(df)
    verdicts_by_name = {v.feature: v for v in report.verdicts}
    assert verdicts_by_name["ret_1m"].classification == "SAFE"
    assert verdicts_by_name["ret_3m"].classification == "SAFE"
    assert report.review_count == 0
