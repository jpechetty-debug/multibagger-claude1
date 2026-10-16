"""Offline reconciliation checks using independent source fixtures."""

import csv
import importlib.util
import json
import sqlite3
from collections import Counter
from datetime import date
from pathlib import Path

import polars as pl
import pytest

from ops.enrich_from_local_data import build, load_prices, nse_symbol


def write_csv(path, fields, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        writer.writerows(rows)


def test_reconciliation_preserves_sources_and_separates_observation_dates(tmp_path):
    source = tmp_path / "source.db"
    with sqlite3.connect(source) as conn:
        conn.execute("CREATE TABLE multibaggers(symbol TEXT, price REAL, score REAL, as_of_date TEXT)")
        conn.execute("INSERT INTO multibaggers VALUES ('ABC.NS', 100, 80, '2026-11-14')")
        conn.execute("CREATE TABLE fundamentals_pit(symbol TEXT, as_of_date TEXT)")
        conn.execute("INSERT INTO fundamentals_pit VALUES ('ABC.NS', '2026-08-20')")
    before = source.read_bytes()
    write_csv(tmp_path / "runtime/bhavcopy_history/eq_20261015.csv",
              ["symbol", "series", "Open", "High", "Low", "Close", "Volume"],
              [("ABC", "EQ", 110, 115, 105, 112, 1000),
               ("ABC", "BE", 90, 100, 85, 95, 1000)])
    write_csv(tmp_path / "data/nse_listing_dates.csv",
              ["Symbol", "Listing_Date", "Delisting_Date"], [("ABC", "2010-01-01", "")])
    lake_dir = tmp_path / "data/lake/daily"
    lake_dir.mkdir(parents=True)
    pl.DataFrame({"symbol": ["ABC.NS"], "as_of_date": ["2026-08-20"], "price": [90.0]}).write_parquet(
        lake_dir / "ABC.NS.parquet")
    output = tmp_path / "review.db"
    summary = build(tmp_path, source, output, date(2026, 10, 16))
    assert source.read_bytes() == before
    assert summary["lake_keys_not_in_pit"] == 0
    with sqlite3.connect(output) as conn:
        row = conn.execute("SELECT original_price,local_close,price_date,lake_as_of_date,issues,original_payload FROM local_enrichment").fetchone()
    assert row[:4] == (100, 112, "2026-10-15", "2026-08-20")
    assert "future_fundamental_date" in json.loads(row[4])
    assert json.loads(row[5])["score"] == 80
    with pytest.raises(FileExistsError):
        build(tmp_path, source, output, date(2026, 10, 16))


def test_prices_exclude_future_non_equity_bad_ohlc_and_conflicting_closes(tmp_path):
    fields = ["symbol", "series", "Open", "High", "Low", "Close", "Volume"]
    write_csv(tmp_path / "runtime/bhavcopy_history/eq_20261015.csv", fields,
              [("ABC", "EQ", 10, 11, 9, 10, 100),
               ("BAD", "EQ", 10, 8, 9, 10, 100),
               ("BOND", "GB", 10, 11, 9, 10, 100),
               ("CONFLICT", "EQ", 10, 12, 9, 10, 100),
               ("CONFLICT", "EQ", 10, 12, 9, 11, 100),
               ("CONFLICT", "EQ", 10, 12, 9, 10, 100)])
    write_csv(tmp_path / "runtime/bhavcopy_history/eq_20261017.csv", fields,
              [("ABC", "EQ", 20, 21, 19, 20, 100)])
    counts = Counter()
    prices = load_prices(tmp_path, date(2026, 10, 16), [], counts)
    assert prices["ABC.NS"][2] == 10
    assert prices["CONFLICT.NS"][2] is None
    assert "BAD.NS" not in prices and "BOND.NS" not in prices
    assert counts["future_price_files_skipped"] == 1
    assert nse_symbol("ABC.BO") is None


def test_lake_default_ignores_working_directory_and_reads_do_not_create_folders(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "modules/data_layer/parquet/lake_manager.py"
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("isolated_lake_manager", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.DATA_LAKE_PATH == path.parents[3] / "data/lake"
    assert not (tmp_path / "data").exists()
    manager = module.ParquetLakeManager(tmp_path / "custom")
    assert manager.read_symbol_history("MISSING.NS").is_empty()
    assert not (tmp_path / "custom").exists()
    manager.write_symbol_history("ABC.NS", pl.DataFrame({"price": [100]}))
    assert manager.read_symbol_history("ABC.NS")["price"].to_list() == [100]
