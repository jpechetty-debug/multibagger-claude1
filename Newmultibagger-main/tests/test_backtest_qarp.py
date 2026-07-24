import pandas as pd

from scripts.internal import backtest_qarp


def test_capped_qarp_universe_is_seeded_and_not_file_order(monkeypatch):
    tickers = ["FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "FIRST.BO"]
    monkeypatch.setattr(backtest_qarp, "TICKERS", tickers)

    sample = backtest_qarp._build_test_universe(3, sample_seed=7)

    assert sample == backtest_qarp._build_test_universe(3, sample_seed=7)
    assert len(sample) == 3
    assert sample != tickers[:3]
    assert backtest_qarp._build_test_universe(0) == tickers[:5]


def test_qarp_selection_skips_underdiversified_rebalances():
    snapshot = pd.DataFrame(
        {
            "Symbol": [f"STOCK{i}" for i in range(9)],
            "total_score": list(range(9)),
        }
    )

    assert backtest_qarp._select_top_picks(snapshot, min_positions=10).empty

    diversified_snapshot = pd.concat(
        [snapshot, pd.DataFrame({"Symbol": ["STOCK9"], "total_score": [9]})],
        ignore_index=True,
    )
    picks = backtest_qarp._select_top_picks(diversified_snapshot, min_positions=10)

    assert len(picks) == 10
    assert picks.iloc[0]["Symbol"] == "STOCK9"
