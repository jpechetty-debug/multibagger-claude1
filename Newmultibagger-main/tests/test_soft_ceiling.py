"""Unit tests for the saturating score ceiling in modules/scoring/ceiling.py."""

import pytest

from modules.scoring.ceiling import SOFT_CEILING_BAND, _apply_soft_ceiling


@pytest.mark.parametrize("ceiling", [40.0, 57.5, 60.0, 75.0])
def test_never_exceeds_ceiling(ceiling):
    for score in [0, ceiling - 10, ceiling - 1, ceiling, ceiling + 5, ceiling + 40, 150]:
        assert _apply_soft_ceiling(score, ceiling) <= ceiling


def test_passthrough_below_knee():
    assert _apply_soft_ceiling(50.0, 60.0) == 50.0
    assert _apply_soft_ceiling(60.0 - SOFT_CEILING_BAND, 60.0) == pytest.approx(55.0)


def test_no_ceiling_is_identity():
    assert _apply_soft_ceiling(87.3, 100.0) == 87.3


def test_strictly_increasing_above_cap():
    """The old hard clip mapped 61, 75 and 95 all to 60; order must now survive."""
    outs = [_apply_soft_ceiling(s, 60.0) for s in (56, 58, 60, 61, 65, 75, 95)]
    assert all(b > a for a, b in zip(outs, outs[1:], strict=False))


def test_continuous_at_knee():
    knee = 60.0 - SOFT_CEILING_BAND
    assert _apply_soft_ceiling(knee + 1e-6, 60.0) == pytest.approx(knee, abs=1e-5)
