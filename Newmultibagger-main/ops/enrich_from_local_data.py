"""Reconcile downloaded data into a separate, dated review database; no network access.

Run from any directory: python path/to/ops/enrich_from_local_data.py --as-of 2026-10-16
Original prices/scores are retained. NSE closing prices have their own observation date.
Older lake observations are review evidence, never automatic fundamental replacements.
"""

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[1]
EQUITY_SERIES = ("EQ", "BE", "SM", "ST", "BZ", "E1")


def nse_symbol(value):
    symbol = str(value or "").strip().upper()
    if not symbol or symbol.endswith(".BO") or symbol.startswith("^"):
        return None
    return symbol if symbol.endswith(".NS") else symbol + ".NS"


def iso_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def read_only(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def record_source(path, sources):
    sources.append({"path": str(path.resolve()), "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})


def load_prices(project, cutoff, sources, counts):
    """Select the latest valid equity close, preserving series and file lineage."""
    latest = {}
    paths = sorted((project / "runtime/bhavcopy_history").glob("eq_*.csv"))
    paths += sorted((project / "runtime/bhavcopy_cache").glob("bhavcopy_*.csv"))
    for path in paths:
        day = datetime.strptime(path.stem.rsplit("_", 1)[1], "%Y%m%d").date()
        if day > cutoff:
            counts["future_price_files_skipped"] += 1
            continue
        record_source(path, sources)
        source_path = str(path.resolve())
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                series = row.get("series", row.get("SctySrs", "")).strip()
                if series not in EQUITY_SERIES:
                    continue
                symbol = nse_symbol(row.get("symbol", row.get("TckrSymb")))
                if symbol is None:
                    counts["invalid_price_symbols"] += 1
                    continue
                if "TradDt" in row and iso_date(row["TradDt"]) != day:
                    counts["price_date_mismatches"] += 1
                    continue
                values = [number(row.get(k, row.get(alt))) for k, alt in (
                    ("Open", "OpnPric"), ("High", "HghPric"), ("Low", "LwPric"),
                    ("Close", "ClsPric"), ("Volume", "TtlTradgVol"))]
                op, high, low, close, volume = values
                if (any(v is None for v in values) or min(op, high, low, close) <= 0
                        or volume < 0 or not low <= min(op, close) <= max(op, close) <= high):
                    counts["invalid_price_rows"] += 1
                    continue
                rank = EQUITY_SERIES.index(series)
                candidate = (day, -rank, close, series, source_path)
                old = latest.get(symbol)
                if old and old[:2] == candidate[:2] and (old[2] is None or abs(old[2] - close) > 0.005):
                    counts["same_day_price_conflicts"] += 1
                    # Conflicting records cannot establish a trusted close for this date.
                    latest[symbol] = (day, -rank, None, series, "conflicting local files")
                elif old is None or candidate[:2] > old[:2]:
                    latest[symbol] = candidate
                counts["valid_price_rows"] += 1
    return latest


def load_listings(project, sources):
    path = project / "data/nse_listing_dates.csv"
    if not path.exists():
        return {}
    record_source(path, sources)
    listings = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            symbol = nse_symbol(row.get("Symbol"))
            if symbol:
                if symbol in listings:
                    raise ValueError(f"Ambiguous duplicate listing metadata: {symbol}")
                listings[symbol] = row
    return listings


def load_lake(project, cutoff, sources, counts):
    import polars as pl

    latest = {}
    keys = set()
    for path in sorted((project / "data/lake/daily").glob("*.parquet")):
        record_source(path, sources)
        for row in pl.read_parquet(path).iter_rows(named=True):
            symbol, day = nse_symbol(row.get("symbol")), iso_date(row.get("as_of_date"))
            counts["lake_rows"] += 1
            if not symbol:
                counts["non_nse_lake_rows_excluded"] += 1
                continue
            if not day or day > cutoff:
                counts["invalid_or_future_lake_rows"] += 1
                continue
            if symbol != nse_symbol(path.stem):
                counts["lake_filename_symbol_mismatches"] += 1
                continue
            key = (symbol, day.isoformat())
            if key in keys:
                raise ValueError(f"Duplicate lake observation: {key}")
            keys.add(key)
            if symbol not in latest or day > iso_date(latest[symbol]["as_of_date"]):
                latest[symbol] = row
    return latest, keys


def build(project, database, output, cutoff, max_price_age=7, progress=None):
    project, database, output = Path(project).resolve(), Path(database).resolve(), Path(output).resolve()
    # Refuse overwrite: source databases and existing review runs remain intact.
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    sources, counts = [], Counter()
    progress = progress or (lambda message: None)
    progress("Reading current picks and historical keys")
    with read_only(database) as source:
        picks = [dict(row) for row in source.execute("SELECT * FROM multibaggers ORDER BY symbol")]
        stored_keys = {(nse_symbol(r[0]), str(r[1])[:10]) for r in source.execute(
            "SELECT symbol, as_of_date FROM fundamentals_pit")}
    progress("Validating downloaded bhavcopy prices")
    prices = load_prices(project, cutoff, sources, counts)
    progress(f"Loaded prices for {len(prices)} symbols; reading listing metadata")
    listings = load_listings(project, sources)
    progress("Reading and comparing the local Parquet lake")
    lake, lake_keys = load_lake(project, cutoff, sources, counts)
    progress(f"Loaded {len(lake_keys)} historical keys; writing review output")
    output.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output)
    try:
        conn.executescript("""
            CREATE TABLE local_enrichment (
                symbol TEXT PRIMARY KEY, original_payload TEXT NOT NULL,
                original_price REAL, fundamental_as_of_date TEXT,
                local_close REAL, price_date TEXT, price_series TEXT, price_file TEXT,
                price_age_calendar_days INTEGER, price_difference_pct REAL,
                listing_date TEXT, delisting_date TEXT, listing_file TEXT,
                lake_as_of_date TEXT, lake_payload TEXT, lake_file TEXT,
                issues TEXT NOT NULL, requires_review INTEGER NOT NULL
            );
            CREATE TABLE source_manifest (path TEXT PRIMARY KEY, bytes INTEGER, sha256 TEXT);
        """)
        for row in picks:
            symbol = nse_symbol(row["symbol"])
            issues = []
            if not symbol:
                issues.append("not_nse_equity")
            published = iso_date(row.get("as_of_date"))
            if not published:
                issues.append("missing_or_invalid_fundamental_date")
            elif published > cutoff:
                issues.append("future_fundamental_date")
            price = prices.get(symbol)
            close = price[2] if price else None
            age = (cutoff - price[0]).days if price else None
            if close is None:
                issues.append("missing_or_conflicting_local_price")
            elif age > max_price_age:
                issues.append("stale_local_price")
            listing = listings.get(symbol, {})
            listed, delisted = iso_date(listing.get("Listing_Date")), iso_date(listing.get("Delisting_Date"))
            if not listed or listed == date(1900, 1, 1):
                issues.append("unverified_listing_date")
            elif listed > cutoff:
                issues.append("not_yet_listed")
            if delisted and delisted <= cutoff:
                issues.append("delisted")
            old_price = number(row.get("price"))
            diff = (close / old_price - 1) * 100 if close is not None and old_price and old_price > 0 else None
            if diff is not None and abs(diff) > 5:
                issues.append("price_difference_over_5pct_compare_observation_dates")
            snapshot = lake.get(symbol)
            for issue in issues:
                counts[issue] += 1
            counts["picks_with_local_price"] += close is not None
            counts["picks_with_listing_metadata"] += bool(listing)
            counts["picks_with_lake_snapshot"] += snapshot is not None
            counts["picks_requiring_review"] += bool(issues)
            values = (row["symbol"], json.dumps(row, allow_nan=False), old_price, row.get("as_of_date"),
                      close, price[0].isoformat() if price else None, price[3] if price else None,
                      price[4] if price else None, age, diff, listing.get("Listing_Date"),
                      listing.get("Delisting_Date"), str(project / "data/nse_listing_dates.csv") if listing else None,
                      snapshot["as_of_date"] if snapshot else None,
                      json.dumps(snapshot, default=str) if snapshot else None,
                      str(project / "data/lake/daily" / f"{symbol}.parquet") if snapshot else None,
                      json.dumps(issues), int(bool(issues)))
            conn.execute("INSERT INTO local_enrichment VALUES (" + ",".join(["?"] * len(values)) + ")", values)
        conn.executemany("INSERT INTO source_manifest VALUES (:path,:bytes,:sha256)", sources)
        conn.commit()
    finally:
        conn.close()
    summary = {"as_of": cutoff.isoformat(), "source_database": str(database),
               "output_database": str(output), "current_picks": len(picks),
               "local_price_symbols": len(prices), "listing_symbols": len(listings),
               "lake_symbols": len(lake), "lake_keys_already_in_pit": len(lake_keys & stored_keys),
               "lake_keys_not_in_pit": len(lake_keys - stored_keys),
               "source_files_hashed": len(sources), "counts": dict(counts),
               "notes": ["Source databases were opened read-only. Original prices and scores are retained.",
                         "Lake data is historical snapshot evidence, not independently verified financial filings.",
                         "Price differences compare different observation times; they are review signals, not proven errors.",
                         "Price age uses calendar days. This output does not recalculate scores or certify investment eligibility."]}
    output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=PROJECT)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat,
                        default=datetime.now(ZoneInfo("Asia/Kolkata")).date())
    args = parser.parse_args()
    output = args.out or args.project / "reports/local_enrichment" / f"{args.as_of}.db"
    summary = build(args.project, args.db or args.project / "runtime/stocks.db", output, args.as_of,
                    progress=lambda message: print(message, file=sys.stderr, flush=True))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
