"""Offline tests for bhavcopy-based price history (modules/adapters/bhavcopy_history.py)."""

from datetime import date, timedelta

import pandas as pd
import pytest

import modules.adapters.bhavcopy_history as bh


def _day(d: date, rows: list[tuple]) -> None:
    pd.DataFrame(
        rows, columns=["symbol", "series", "Open", "High", "Low", "Close", "PrevClose", "Volume"]
    ).to_csv(bh._day_file(d), index=False)


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(bh, "HISTORY_DIR", tmp_path)
    monkeypatch.setattr(bh, "_panel", None)
    monkeypatch.setattr(bh, "_panel_files", frozenset())
    today = date(2026, 10, 6)
    monkeypatch.setattr(bh, "_today_ist", lambda: today)
    days = [today - timedelta(days=i) for i in range(30, 0, -1) if (today - timedelta(days=i)).weekday() < 5]
    monkeypatch.setattr(bh, "_trading_days", lambda s, e: [d for d in days if s <= d <= e])
    return days


def test_back_adjust_bonus_keeps_series_continuous():
    idx = pd.date_range("2026-01-01", periods=4)
    df = pd.DataFrame(
        {"Open": [200, 210, 105, 110], "High": [200, 210, 105, 110], "Low": [200, 210, 105, 110],
         "Close": [200.0, 210.0, 105.0, 110.0], "PrevClose": [195, 200, 105, 105],  # 1:1 bonus on day 3
         "Volume": [100.0, 100.0, 200.0, 200.0]},
        index=idx,
    )
    out = bh._back_adjust(df)
    assert list(out["Close"]) == pytest.approx([100.0, 105.0, 105.0, 110.0])
    assert list(out["Volume"]) == pytest.approx([200.0, 200.0, 200.0, 200.0])


def test_back_adjust_ignores_rounding_noise():
    idx = pd.date_range("2026-01-01", periods=3)
    df = pd.DataFrame(
        {"Open": [100, 101, 102], "High": [100, 101, 102], "Low": [100, 101, 102],
         "Close": [100.0, 101.0, 102.0], "PrevClose": [99.0, 100.05, 101.0], "Volume": [1.0, 1.0, 1.0]},
        index=idx,
    )
    assert list(bh._back_adjust(df)["Close"]) == [100.0, 101.0, 102.0]


def test_get_history_shape_and_filters(cache):
    for i, d in enumerate(cache):
        _day(d, [
            ("TCS", "EQ", 100 + i, 101 + i, 99 + i, 100.0 + i, 99.0 + i, 1000),
            ("SGBJUN28", "GB", 1, 1, 1, 1.0, 1.0, 1),  # non-equity series dropped
        ])
    hist = bh.get_history("TCS.NS", period="1mo")
    assert list(hist.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert isinstance(hist.index, pd.DatetimeIndex) and hist.index.is_monotonic_increasing
    assert hist["Close"].iloc[-1] == 100.0 + len(cache) - 1
    assert bh.get_history("SGBJUN28", period="1mo").empty
    assert bh.get_history("TCS.BO").empty and bh.get_history("^NSEI").empty


def test_market_wide_prev_close_jump_is_a_gap_not_a_split(cache):
    """A missing session file makes every symbol's PrevClose disagree on one date."""
    gap_day = cache[10]
    for i, d in enumerate(cache):
        rows = []
        for n in range(60):
            # Market moved +5 in an uncached session just before gap_day, so on
            # gap_day NSE's PrevClose (that session's close) != our cached close.
            close = 100.0 + n + (5 if i >= 10 else 0)
            rows.append((f"S{n}", "EQ", close, close, close, close, close, 10))
        _day(d, rows)
    hist = bh.get_history("S0.NS", period="1mo")
    assert hist["Close"].iloc[0] == pytest.approx(100.0)  # not rescaled by a fake split
    assert pd.Timestamp(gap_day) in bh._gap_dates


def test_get_history_empty_when_stale(cache):
    for d in cache[:5]:  # cache stops ~3 weeks before "today"
        _day(d, [("TCS", "EQ", 1, 1, 1, 1.0, 1.0, 1)])
    assert bh.get_history("TCS.NS", period="1mo").empty


def test_get_history_empty_when_window_not_covered(cache):
    for d in cache:
        _day(d, [("TCS", "EQ", 1, 1, 1, 1.0, 1.0, 1)])
    assert bh.get_history("TCS.NS", period="1y").empty  # only ~1 month cached
