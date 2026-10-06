"""Training labels come from real price history, and batch features never look ahead."""

import pandas as pd
import pytest

from modules import target_engineering as te
from modules.feature_factory import compute_features_batch


@pytest.fixture
def closes(monkeypatch):
    prices = pd.DataFrame(
        [
            ("AAA.NS", "2026-06-08", 100.0),  # entry: last close on/before snapshot
            ("AAA.NS", "2026-09-10", 130.0),  # exit: first close on/after +3M
            ("BBB.NS", "2026-06-09", 50.0),   # no close near +3M -> unlabeled
        ],
        columns=["symbol", "date", "close"],
    )
    prices["date"] = pd.to_datetime(prices["date"])
    monkeypatch.setattr("modules.data_layer.price_history.load_closes", lambda: prices.copy())


def test_forward_return_from_adjusted_closes(closes):
    pit = pd.DataFrame({"symbol": ["AAA.NS", "BBB.NS"], "as_of_date": ["2026-06-09", "2026-06-09"], "pit_price": [999.0, 50.0]})
    out = te.build_training_targets(pit, horizon_months=3)
    assert list(out["symbol"]) == ["AAA.NS"]
    row = out.iloc[0]
    # snapshot price (999) is ignored: entry and exit share one adjusted series
    assert row["entry_price"] == 100.0 and row["forward_price"] == 130.0
    assert row["forward_return"] == pytest.approx(0.30)
    assert row["is_multibagger"] == 1  # > 15% threshold for 3M


def test_unelapsed_horizon_is_dropped(closes):
    pit = pd.DataFrame({"symbol": ["AAA.NS"], "as_of_date": ["2026-09-10"], "pit_price": [130.0]})
    assert te.build_training_targets(pit, horizon_months=3).empty


def test_sector_features_ranked_per_date_not_across_dates():
    # Same symbol on two dates: the early row must not see the later row's return.
    df = pd.DataFrame({
        "symbol": ["AAA.NS", "BBB.NS", "AAA.NS", "BBB.NS"],
        "as_of_date": ["2026-06-09", "2026-06-09", "2026-09-09", "2026-09-09"],
        "sector": ["IT"] * 4,
        "ret_3m": [10.0, 20.0, 90.0, 5.0],
        "pe_ratio": [10.0, 30.0, 40.0, 40.0],
    })
    feats = compute_features_batch(df)
    assert list(feats["sector_rs_rank"]) == [0.5, 1.0, 1.0, 0.5]
    assert feats["pe_vs_sector_median"].iloc[0] == pytest.approx(10 / 20 - 1)
    assert feats["pe_vs_sector_median"].iloc[2] == pytest.approx(0.0)
