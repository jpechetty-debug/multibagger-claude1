"""Synthetic sibling-project fixtures; no network or real databases required."""

import json
import sqlite3
from datetime import date

import pytest

from ops.import_external_data import checkpointed_source, field_candidate, import_external, price_is_valid


def test_import_normalizes_growth_keeps_raw_values_and_checks_issuer(tmp_path):
    base, source, output = (tmp_path / name for name in ("base.db", "source.db", "output.db"))
    with sqlite3.connect(base) as conn:
        conn.execute("CREATE TABLE local_enrichment(symbol TEXT,original_payload TEXT)")
        conn.execute("INSERT INTO local_enrichment VALUES (?,?)", ("SYNTHETIC.NS", json.dumps({"score": 77, "sales_cagr_5y": None})))
    doc = {"document_id": "fixture", "published_at": "2026-04-01T12:00:00Z",
           "publication_verified": 1, "ingested_at": "2026-10-15T12:00:00Z"}
    quality = {"scope": "consolidated", "currency": "INR", "metrics": {},
               "growth_windows": {"sales": {"cagr": 0.17, "cagr_pct": 17, "years": 5, "observations": 6, "end": "2026-03-31"}},
               "field_sources": {"sales_cagr_5y": {"document_ids": ["fixture"]}}}
    with sqlite3.connect(source) as conn:
        conn.executescript("""
            CREATE TABLE symbol_master(symbol TEXT,isin TEXT,board TEXT);
            INSERT INTO symbol_master VALUES ('SYNTHETIC','SYNTHETIC-ISIN','mainboard');
            CREATE TABLE fundamentals(symbol TEXT,sales_cagr_5y REAL,financial_quality TEXT);
            CREATE TABLE financial_history(symbol TEXT,year INTEGER);
            CREATE TABLE quarterly_results(symbol TEXT,period_end TEXT);
            CREATE TABLE price_treatments(symbol TEXT,id INTEGER);
            CREATE TABLE prices(symbol TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL);
            INSERT INTO prices VALUES ('SYNTHETIC.NS','2026-10-15',100,110,90,105,1000);
            CREATE TABLE history_documents(document_id TEXT,published_at TEXT,publication_verified INTEGER,ingested_at TEXT);
        """)
        conn.execute("INSERT INTO fundamentals VALUES (?,?,?)", ("SYNTHETIC.NS", 0.17, json.dumps(quality)))
        conn.execute("INSERT INTO history_documents VALUES (:document_id,:published_at,:publication_verified,:ingested_at)", doc)
    cache = tmp_path / "runtime/bhavcopy_cache"
    cache.mkdir(parents=True)
    (cache / "bhavcopy_20261015.csv").write_text("TckrSymb,SctySrs,ISIN\nSYNTHETIC,EQ,SYNTHETIC-ISIN\n", encoding="utf-8")
    before = source.read_bytes(), base.read_bytes()
    result = import_external(base, source, [], output, date(2026, 10, 16), project=tmp_path)
    assert (source.read_bytes(), base.read_bytes()) == before
    assert result["counts"]["missing_targets_with_usable_evidence"] == 1
    with sqlite3.connect(output) as conn:
        candidate = conn.execute("SELECT candidate_value,target_units,identity_status,evidence_status FROM field_candidates").fetchone()
        assert candidate == (17, "percent", "isin_match", "evidence_usable_for_review")
        raw = json.loads(conn.execute("SELECT payload FROM external_rows WHERE source_table='fundamentals'").fetchone()[0])
        assert raw["sales_cagr_5y"] == 0.17
        original = json.loads(conn.execute("SELECT original_payload FROM local_enrichment").fetchone()[0])
        assert original["score"] == 77 and original["sales_cagr_5y"] is None


def test_future_publication_and_incomplete_growth_window_are_flagged():
    q = {"scope": "consolidated", "currency": "INR",
         "metrics": {"roe": {"value": 20, "status": "derived", "period_end": "2026-03-31"}},
         "field_sources": {"roe": {"document_id": "future"}}}
    def lookup(key):
        return {"publication_verified": 1, "published_at": "2026-11-01", "ingested_at": "2026-10-15"}
    candidate = field_candidate({"roe": 20}, q, "roe", date(2026, 10, 16), lookup)
    assert "field_documents_not_available_by_cutoff" in candidate[-1]
    q["growth_windows"] = {"sales": {"cagr": 0.2, "years": 3, "observations": 4, "end": "2026-03-31"}}
    candidate = field_candidate({"sales_cagr_5y": 0.2}, q, "sales_cagr_5y", date(2026, 10, 16), lookup)
    assert "five_year_window_not_verified" in candidate[-1]


def test_mutating_or_uncheckpointed_external_database_is_rejected(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE example(value INTEGER)")
    with pytest.raises(ValueError, match="changed during extraction"):
        with checkpointed_source(source):
            with sqlite3.connect(source) as conn:
                conn.execute("INSERT INTO example VALUES (1)")
    source.with_name("source.db-wal").write_bytes(b"uncheckpointed fixture")
    with pytest.raises(ValueError, match="uncheckpointed WAL"):
        with checkpointed_source(source):
            pass
    assert not price_is_valid({"date": "2026-10-17", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 1}, date(2026, 10, 16))
