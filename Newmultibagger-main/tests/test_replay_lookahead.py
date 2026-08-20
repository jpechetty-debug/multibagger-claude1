import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db.repository as database


def test_research_replay_strict_lookahead_boundary(tmp_path, monkeypatch):
    """
    Test Issue #7: Research Replay must guarantee that MAX(as_of_date) <= REPLAY_DATE
    and no future rows leak into the returned dataframe.
    """
    db_path = tmp_path / "replay_lookahead.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    conn = database.get_connection()
    try:
        # Insert historical PIT data spanning multiple periods including future dates
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (symbol, as_of_date, score, sales_cagr_5y, avg_roe_5y)
            VALUES
            ('AAA.NS', '2017-06-30', 50, 10.0, 15.0),
            ('AAA.NS', '2017-12-31', 60, 12.0, 16.0),
            ('AAA.NS', '2018-03-31', 75, 14.0, 18.0),
            ('AAA.NS', '2018-09-30', 80, 16.0, 19.0),
            ('BBB.NS', '2017-12-31', 40, 8.0, 10.0),
            ('BBB.NS', '2018-06-30', 85, 20.0, 22.0)
            """
        )
        conn.commit()
    finally:
        conn.close()

    # REPLAY SCENARIO: We are running research on Jan 1st, 2018
    # We should NOT see any data from 2018-03-31, 2018-06-30, or 2018-09-30
    replay_date = "2018-01-01"

    df, snap_date = database.load_fundamentals_universe_as_of(replay_date)

    # Validate snapshot date itself doesn't exceed replay date
    assert snap_date <= replay_date, f"Snapshot date {snap_date} leaked past replay date {replay_date}"

    # Validate dataframe rows strictly enforce boundary
    assert not df.empty, "Dataframe should return available historical records"
    
    symbols = df["symbol"].tolist()
    assert "AAA.NS" in symbols
    assert "BBB.NS" in symbols

    # Check AAA.NS strictly matches the state known exactly on 2018-01-01
    aaa_row = df[df["symbol"] == "AAA.NS"].iloc[0]
    assert aaa_row["score"] == 60, f"Expected 2017-12-31 score (60), got future score {aaa_row['score']}"
    assert aaa_row["as_of_date"] == "2017-12-31", f"Expected as_of_date 2017-12-31, got {aaa_row['as_of_date']}"

    # Check BBB.NS strictly matches the state known exactly on 2018-01-01
    bbb_row = df[df["symbol"] == "BBB.NS"].iloc[0]
    assert bbb_row["score"] == 40, f"Expected 2017-12-31 score (40), got future score {bbb_row['score']}"
    assert bbb_row["as_of_date"] == "2017-12-31", f"Expected as_of_date 2017-12-31, got {bbb_row['as_of_date']}"


def test_missing_data_before_history_begins(tmp_path, monkeypatch):
    """
    If we replay a date before ANY data exists, it should return an empty universe,
    not default to the earliest available future data.
    """
    db_path = tmp_path / "replay_missing.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    conn = database.get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (symbol, as_of_date, score)
            VALUES
            ('AAA.NS', '2019-01-01', 50)
            """
        )
        conn.commit()
    finally:
        conn.close()

    # Replay before history starts
    df, snap_date = database.load_fundamentals_universe_as_of("2018-01-01")

    assert df.empty, "Dataframe should be empty when replaying before history exists"
    assert snap_date is None, "Snapshot date should be None"
