import sys
import types
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import db.repository as database  # noqa: E402


def _sample_universe():
    return pd.DataFrame(
        [
            {
                "Symbol": "AAA.NS",
                "Price": 100.0,
                "Sector": "Technology",
                "Score": 82,
                "Sales_Growth_5Y%": 14.0,
                "Avg_ROE_5Y%": 19.0,
                "PE_Ratio": 22.0,
                "Debt_Equity": 0.2,
                "Market_Cap_Cr": 1200.0,
                "CFO_PAT_Ratio": 1.4,
            },
            {
                "Symbol": "BBB.NS",
                "Price": 200.0,
                "Sector": "Financial",
                "Score": 78,
                "Sales_Growth_5Y%": 11.5,
                "Avg_ROE_5Y%": 17.5,
                "PE_Ratio": 16.0,
                "Debt_Equity": 0.4,
                "Market_Cap_Cr": 2200.0,
                "CFO_PAT_Ratio": 1.1,
            },
        ]
    )


def test_save_multibaggers_writes_pit_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    database.save_multibaggers(_sample_universe())

    conn = database.get_connection()
    try:
        multibaggers = pd.read_sql(
            "SELECT symbol, as_of_date FROM multibaggers ORDER BY symbol",
            conn,
        )
        pit = pd.read_sql(
            """
            SELECT symbol, as_of_date, sales_cagr_5y, avg_roe_5y
            FROM fundamentals_pit
            ORDER BY symbol
            """,
            conn,
        )
    finally:
        conn.close()

    assert len(multibaggers) == 2
    assert len(pit) == 2
    assert all(isinstance(v, str) and len(v) == 10 for v in multibaggers["as_of_date"])
    assert list(pit["symbol"]) == ["AAA.NS", "BBB.NS"]


def test_load_fundamentals_universe_as_of_returns_latest_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67_lookup.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    conn = database.get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (symbol, as_of_date, score, sales_cagr_5y, avg_roe_5y)
            VALUES
            ('AAA.NS', '2026-01-01', 70, 10.0, 15.0),
            ('AAA.NS', '2026-01-15', 80, 12.0, 18.0),
            ('BBB.NS', '2026-01-15', 75, 11.0, 16.0)
            """
        )
        conn.commit()
    finally:
        conn.close()

    df_old, snap_old = database.load_fundamentals_universe_as_of("2026-01-10")
    df_new, snap_new = database.load_fundamentals_universe_as_of("2026-01-31")

    assert snap_old == "2026-01-01"
    assert len(df_old) == 1
    assert df_old.iloc[0]["symbol"] == "AAA.NS"

    assert snap_new == "2026-01-15"
    assert set(df_new["symbol"].tolist()) == {"AAA.NS", "BBB.NS"}


def test_pit_retention_prunes_old_snapshots(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67_retention.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    conn = database.get_connection()
    try:
        today = datetime.now().date().isoformat()
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (symbol, as_of_date, score)
            VALUES
            ('OLD.NS', '2000-01-01', 50),
            ('NEW.NS', ?, 90)
            """,
            (today,),
        )
        conn.commit()
    finally:
        conn.close()

    deleted = database.prune_fundamentals_pit_retention(keep_days=30)

    conn = database.get_connection()
    try:
        remaining = pd.read_sql(
            "SELECT symbol, as_of_date FROM fundamentals_pit ORDER BY symbol",
            conn,
        )
    finally:
        conn.close()

    # Issue #1 Fix: Retention should never delete fundamentals_pit
    assert deleted == 0
    assert len(remaining) == 2
    assert "OLD.NS" in remaining["symbol"].values


def test_publication_lag_lookahead():
    """
    Simulate a request for data before the release_lag_map allows it.
    It should raise a PITViolationError or return no data.
    """
    from modules.pit_auditor import enforce_pit_gate, PITViolationError
    import pytest

    # If the quarter ended March 31, 2026, and we check April 15, 2026 (15 days), it should block (needs 45 days)
    with pytest.raises(PITViolationError):
        enforce_pit_gate(as_of_date="2026-04-15", quarter_end_date="2026-03-31", symbol="TEST.NS")


def test_retroactive_revision_append(tmp_path, monkeypatch):
    """
    Prove that inserting a restated filing for the same report period on a new 
    as_of_date preserves both versions in PITDataStore.
    """
    from modules.pit_auditor import PITDataStore
    db_path = tmp_path / "pit_store_revisions.db"
    
    store = PITDataStore(db_name=str(db_path))
    
    # Original filing on May 15
    store.insert_record(
        symbol="AAA.NS",
        metric_name="earnings",
        value=100.0,
        report_date="2026-03-31",
        as_of_date="2026-05-15",
        source="vendor"
    )
    
    # Restated filing on June 10
    store.insert_record(
        symbol="AAA.NS",
        metric_name="earnings",
        value=80.0,
        report_date="2026-03-31", # Same report date
        as_of_date="2026-06-10",  # New observed date
        source="vendor"
    )

    import sqlite3
    conn = sqlite3.connect(str(db_path))
    df = pd.read_sql("SELECT * FROM pit_data WHERE symbol='AAA.NS' ORDER BY as_of_date", conn)
    conn.close()
    
    assert len(df) == 2, "Both revisions should be preserved in the store"
    assert df.iloc[0]["value"] == 100.0
    assert df.iloc[1]["value"] == 80.0


def test_get_fundamentals_snapshot_as_of_returns_latest_prior_snapshot(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67_point_lookup.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    database.init_db()
    conn = database.get_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO fundamentals_pit
            (symbol, as_of_date, score, sales_cagr_5y, avg_roe_5y)
            VALUES
            ('AAA.NS', '2026-01-01', 60, 8.0, 14.0),
            ('AAA.NS', '2026-01-15', 88, 12.0, 18.0)
            """
        )
        conn.commit()
    finally:
        conn.close()

    snapshot = database.get_fundamentals_snapshot_as_of("AAA.NS", "2026-01-20")
    missing = database.get_fundamentals_snapshot_as_of("AAA.NS", "2025-12-31")

    assert snapshot["as_of_date"] == "2026-01-15"
    assert snapshot["score"] == 88
    assert missing is None


def test_write_fundamentals_snapshot_normalizes_dates_and_syncs_pit_store(tmp_path, monkeypatch):
    db_path = tmp_path / "phase67_snapshot_contract.db"
    monkeypatch.setattr(database, "DB_NAME", str(db_path), raising=False)

    inserted_records = []

    class FakePITStore:
        def insert_record(self, *args):
            inserted_records.append(args)

        def close(self):
            inserted_records.append(("closed",))

    monkeypatch.setitem(
        sys.modules,
        "modules.pit_auditor",
        types.SimpleNamespace(
            PITDataStore=FakePITStore,
            sanitize=lambda df: df,  # Pass-through mock for sanitization
        ),
    )

    database.init_db()
    database._write_fundamentals_snapshot(
        pd.DataFrame(
            [
                {
                    "symbol": "AAA.NS",
                    "as_of_date": "2026-02-20T15:45:00",
                    "price": 101.5,
                    "sector": "Technology",
                    "score": 91.0,
                    "sales_cagr_5y": 18.2,
                    "avg_roe_5y": 24.6,
                    "pe_ratio": 19.4,
                    "debt_equity": 0.25,
                    "market_cap_cr": 4200.0,
                    "cfo_pat_ratio": 1.35,
                    "promoter_holding": 62.34,
                    "fii_holding": 15.11,
                    "dii_holding": 9.87,
                    "updated_at": pd.Timestamp("2026-02-19 10:15:30"),
                }
            ]
        )
    )

    conn = database.get_connection()
    try:
        snapshot_row = pd.read_sql(
            """
            SELECT symbol, as_of_date, source_updated_at, score, sales_cagr_5y,
                   promoter_holding, fii_holding, dii_holding
            FROM fundamentals_pit
            """,
            conn,
        ).iloc[0]
    finally:
        conn.close()

    metric_names = {args[1] for args in inserted_records if args and args[0] != "closed"}

    assert snapshot_row["symbol"] == "AAA.NS"
    assert snapshot_row["as_of_date"] == "2026-02-20"
    assert snapshot_row["source_updated_at"] == "2026-02-19 10:15:30"
    assert snapshot_row["promoter_holding"] == 62.34
    assert snapshot_row["fii_holding"] == 15.11
    assert snapshot_row["dii_holding"] == 9.87
    assert {
        "score",
        "sales_cagr_5y",
        "avg_roe_5y",
        "pe_ratio",
        "debt_equity",
        "cfo_pat_ratio",
        "market_cap_cr",
        "promoter_holding",
        "fii_holding",
        "dii_holding",
    } <= metric_names
    assert inserted_records[-1] == ("closed",)
