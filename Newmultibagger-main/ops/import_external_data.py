"""Add explicitly selected sibling-project downloads to an existing enrichment review.

All inputs are read-only. Source WAL must be empty and source metadata must remain
unchanged during extraction. Imports preserve observations, units, and adjustment
bases; field comparisons never overwrite live scores or claim period equivalence.
"""

import argparse
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ops.enrich_from_local_data import EQUITY_SERIES, PROJECT, iso_date, nse_symbol, number, read_only

MAPPINGS = (
    ("roe", "roe", 1, "percent"),
    ("roce", "roce", 1, "percent"),
    ("debt_equity", "debt_equity", 1, "ratio"),
    ("cfo_pat_ratio", "cfo_pat_ratio", 1, "ratio"),
    ("roa", "roa_pct", 1, "percent"),
    ("sales_cagr_5y", "sales_cagr_5y", 100, "percent"),
    ("profit_cagr_5y", "pat_cagr_5y", 100, "percent"),
)


def dump(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, default=str)


def known_day(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo:
            stamp = stamp.astimezone(ZoneInfo("Asia/Kolkata"))
        return stamp.date()
    except (TypeError, ValueError):
        return None


@contextmanager
def checkpointed_source(path):
    """Read an externally owned checkpoint without creating WAL/SHM files there."""
    path = Path(path).resolve()
    wal = Path(str(path) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError(f"Source has uncheckpointed WAL; supply a consistent snapshot: {path}")
    before = path.stat()
    conn = sqlite3.connect(path.as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        yield conn, {"path": str(path), "bytes": before.st_size, "mtime_ns": before.st_mtime_ns}
        after = path.stat()
        if ((after.st_size, after.st_mtime_ns) != (before.st_size, before.st_mtime_ns)
                or (wal.exists() and wal.stat().st_size)):
            raise ValueError(f"Source changed during extraction; discard and rerun: {path}")
    finally:
        conn.close()


def document_ids(value):
    result = set()
    if isinstance(value, dict):
        if value.get("document_id"):
            result.add(value["document_id"])
        result.update(value.get("document_ids") or [])
        for child in value.values():
            result.update(document_ids(child))
    elif isinstance(value, list):
        for child in value:
            result.update(document_ids(child))
    return result


def price_is_valid(row, cutoff):
    day = iso_date(row["date"])
    vals = [number(row[k]) for k in ("open", "high", "low", "close", "volume")]
    if not day or day > cutoff or any(v is None for v in vals):
        return False
    op, high, low, close, volume = vals
    return min(op, high, low, close) > 0 and volume >= 0 and low <= min(op, close) <= max(op, close) <= high


def local_identities(project, cutoff):
    files = [p for p in (project / "runtime/bhavcopy_cache").glob("bhavcopy_*.csv")
             if datetime.strptime(p.stem.split("_")[-1], "%Y%m%d").date() <= cutoff]
    if not files:
        return {}, None
    path = max(files)
    result = {}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if row.get("SctySrs") in EQUITY_SERIES and row.get("ISIN"):
                symbol = nse_symbol(row.get("TckrSymb"))
                result.setdefault(symbol, set()).add(row["ISIN"].strip())
    return result, {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def field_candidate(row, quality, source_field, cutoff, document_lookup):
    """Retain field-specific proof; no top-level publication inheritance."""
    value = number(row.get(source_field))
    if value is None:
        return None
    proof = quality.get("metrics", {}).get(source_field) or {}
    reasons = []
    if source_field.endswith("_cagr_5y"):
        window = quality.get("growth_windows", {}).get("sales" if source_field == "sales_cagr_5y" else "profit", {})
        proof = {"window": window}
        if (number(window.get("cagr")) is None or not math.isclose(value, number(window["cagr"]), rel_tol=1e-8, abs_tol=1e-8)
                or not 4.95 <= (number(window.get("years")) or 0) <= 5.05
                or (number(window.get("observations")) or 0) < 6):
            reasons.append("five_year_window_not_verified")
        period = window.get("end")
    else:
        if (proof.get("status") != "derived" or proof.get("reasons")
                or number(proof.get("value")) is None
                or not math.isclose(value, number(proof.get("value")) or 0, rel_tol=1e-8, abs_tol=1e-8)):
            reasons.append("metric_derivation_not_verified")
        period = proof.get("period_end")
    if not iso_date(period) or iso_date(period) > cutoff:
        reasons.append("missing_or_future_period")
    if quality.get("scope") not in {"consolidated", "standalone"} or quality.get("currency") != "INR":
        reasons.append("scope_or_currency_unverified")
    field_source = quality.get("field_sources", {}).get(source_field) or {}
    refs = document_ids([proof, field_source])
    if not refs:
        reasons.append("missing_field_documents")
    documents = [document_lookup(doc) for doc in sorted(refs)]
    if any(not doc or not doc.get("publication_verified")
           or not known_day(doc.get("published_at")) or known_day(doc["published_at"]) > cutoff
           or not known_day(doc.get("ingested_at")) or known_day(doc["ingested_at"]) > cutoff
           for doc in documents):
        reasons.append("field_documents_not_available_by_cutoff")
    # Preserve source-reported conflicts rather than granting a good top-level score.
    reconciliation = quality.get("source_reconciliation") or {}
    if reconciliation.get("unresolved_conflicts"):
        reasons.append("source_reconciliation_conflicts")
    return value, period, {"metric": proof, "field_source": field_source}, refs, reasons


def import_external(base, external_db, archive_dbs, output, cutoff, project=PROJECT):
    output = Path(output).resolve()
    if output.exists() or output.with_suffix(".summary.json").exists():
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".building")
    if temp.exists():
        raise FileExistsError(temp)
    counts, manifests = Counter(), []
    identities, identity_source = local_identities(Path(project), cutoff)
    if identity_source:
        manifests.append(identity_source)
    out = sqlite3.connect(temp)
    try:
        with read_only(base) as local:
            local.backup(out)
        local_rows = {r[0]: json.loads(r[1]) for r in out.execute("SELECT symbol,original_payload FROM local_enrichment")}
        out.executescript("""
            CREATE TABLE external_rows(source_db TEXT, source_table TEXT, symbol TEXT, row_key TEXT,
                payload TEXT NOT NULL, PRIMARY KEY(source_db,source_table,symbol,row_key));
            CREATE TABLE external_documents(document_id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE field_candidates(symbol TEXT,target_field TEXT,source_field TEXT,
                original_value REAL,candidate_value REAL,target_units TEXT,period_end TEXT,
                scope TEXT,currency TEXT,identity_status TEXT,evidence_status TEXT,
                target_missing INTEGER,proof TEXT,document_ids TEXT,issues TEXT,
                PRIMARY KEY(symbol,target_field));
            CREATE TABLE external_prices(source_db TEXT,symbol TEXT,date TEXT,open REAL,high REAL,
                low REAL,close REAL,volume REAL,adjustment_basis TEXT,chunk_id INTEGER,
                PRIMARY KEY(source_db,symbol,date));
            CREATE TABLE external_chunks(source_db TEXT,chunk_id INTEGER,payload TEXT,
                PRIMARY KEY(source_db,chunk_id));
            CREATE TABLE external_run_manifest(payload TEXT NOT NULL);
        """)
        with checkpointed_source(external_db) as (source, manifest):
            manifests.append(manifest)
            masters = {}
            for r in source.execute("SELECT * FROM symbol_master"):
                sym = nse_symbol(r["symbol"])
                if sym in local_rows:
                    masters.setdefault(sym, []).append(dict(r))
            document_cache = {}

            def document_lookup(doc_id):
                if doc_id not in document_cache:
                    result = source.execute("SELECT * FROM history_documents WHERE document_id=?", (doc_id,)).fetchone()
                    document_cache[doc_id] = dict(result) if result else None
                return document_cache[doc_id]

            for symbol, original in local_rows.items():
                issuer_rows = masters.get(symbol, [])
                isins = {r["isin"] for r in issuer_rows if r.get("isin")}
                local_isins = identities.get(symbol, set())
                identity = ("isin_match" if len(isins) == len(local_isins) == 1 and isins == local_isins
                            else "isin_conflict" if isins and local_isins and isins != local_isins
                            else "exact_symbol_only")
                if issuer_rows:
                    counts["picks_with_external_identity"] += 1
                counts[identity] += 1
                for r in issuer_rows:
                    out.execute("INSERT INTO external_rows VALUES (?,?,?,?,?)",
                                (str(external_db), "symbol_master", symbol, r.get("board", ""), dump(r)))
                for table, key in (("fundamentals", "symbol"), ("financial_history", "year"),
                                   ("quarterly_results", "period_end"), ("price_treatments", "id")):
                    rows = [dict(r) for r in source.execute(f"SELECT * FROM {table} WHERE symbol=?", (symbol,))]
                    counts[table + "_symbols"] += bool(rows)
                    for r in rows:
                        out.execute("INSERT INTO external_rows VALUES (?,?,?,?,?)",
                                    (str(external_db), table, symbol, str(r[key]), dump(r)))
                        counts[table + "_rows"] += 1
                    if table != "fundamentals" or not rows:
                        continue
                    row = rows[0]
                    quality = json.loads(row.get("financial_quality") or "{}")
                    for source_field, target_field, scale, units in MAPPINGS:
                        candidate = field_candidate(row, quality, source_field, cutoff, document_lookup)
                        if candidate is None:
                            continue
                        raw, period, proof, refs, issues = candidate
                        if identity != "isin_match":
                            issues.append("issuer_identity_requires_review")
                        original_value = number(original.get(target_field))
                        status = "evidence_usable_for_review" if not issues else "needs_evidence_review"
                        out.execute("INSERT INTO field_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                    (symbol, target_field, source_field, original_value, raw * scale, units,
                                     period, quality.get("scope"), quality.get("currency"), identity, status,
                                     int(original_value is None), dump(proof), dump(sorted(refs)), dump(issues)))
                        counts[status] += 1
                        counts["missing_target_field_candidates"] += original_value is None
                        counts["missing_targets_with_usable_evidence"] += original_value is None and not issues
                # These prices were normalized by the other project; preserve treatment records separately.
                batch = []
                for r in source.execute("SELECT * FROM prices WHERE symbol=? ORDER BY date", (symbol,)):
                    if price_is_valid(r, cutoff):
                        batch.append((str(external_db), symbol, r["date"], r["open"], r["high"], r["low"],
                                      r["close"], r["volume"], "external_project_normalized_see_price_treatments", None))
                    else:
                        counts["excluded_external_prices"] += 1
                out.executemany("INSERT INTO external_prices VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
                counts["normalized_price_rows"] += len(batch)
            for doc_id, doc in document_cache.items():
                if doc:
                    out.execute("INSERT INTO external_documents VALUES (?,?)", (doc_id, dump(doc)))
            counts["source_documents_retained"] = len(document_cache)
        for path in archive_dbs:
            with checkpointed_source(path) as (source, manifest):
                manifests.append(manifest)
                plan_row = source.execute("SELECT value FROM meta WHERE key='plan'").fetchone()
                plan = json.loads(plan_row[0]) if plan_row else {}
                basis = plan.get("basis", "provider_adjusted_unknown")
                for symbol in local_rows:
                    batch, chunks = [], set()
                    for r in source.execute("SELECT * FROM bars WHERE symbol=? ORDER BY date", (symbol,)):
                        if price_is_valid(r, cutoff):
                            batch.append((str(path), symbol, r["date"], r["open"], r["high"], r["low"],
                                          r["close"], r["volume"], basis, r["chunk_id"]))
                            chunks.add(r["chunk_id"])
                        else:
                            counts["excluded_archive_prices"] += 1
                    out.executemany("INSERT INTO external_prices VALUES (?,?,?,?,?,?,?,?,?,?)", batch)
                    counts["archive_price_rows"] += len(batch)
                    counts["archive_price_symbols"] += bool(batch)
                    for chunk in chunks:
                        r = source.execute("SELECT * FROM chunks WHERE id=?", (chunk,)).fetchone()
                        if not r or r["status"] != "saved" or not known_day(r["observed_at"]) or known_day(r["observed_at"]) > cutoff:
                            raise ValueError(f"Missing, incomplete or future archive evidence: {path} chunk {chunk}")
                        out.execute("INSERT OR IGNORE INTO external_chunks VALUES (?,?,?)", (str(path), chunk, dump(dict(r))))
        out.execute("CREATE INDEX external_prices_symbol_date ON external_prices(symbol,date)")
        out.execute("CREATE INDEX external_rows_symbol_table ON external_rows(symbol,source_table)")
        summary = {"as_of": cutoff.isoformat(), "base_review": str(Path(base).resolve()),
                   "output": str(output), "current_picks": len(local_rows), "sources": manifests,
                   "counts": dict(counts),
                   "price_range": out.execute("SELECT MIN(date),MAX(date) FROM external_prices").fetchone(),
                   "notes": ["Original application databases, downloaded files, prices and scores remain unchanged.",
                             "Field candidates require target fiscal-period, scope and formula compatibility review before adoption.",
                             "Current financial_history/quarterly_results projections are reference rows, not independently PIT-certified vintages.",
                             "Price sources keep separate adjustment bases; overlapping rows are not concatenated into one return series.",
                             "Archive chunk lineage is retained; original response bodies/hashes have not been revalidated in this import.",
                             "Financial field document metadata is retained; original source blobs remain in the source database."]}
        out.execute("INSERT INTO external_run_manifest VALUES (?)", (dump(summary),))
        out.commit()
        if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Output database integrity check failed")
        out.close()
        temp.rename(output)
        output.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return summary
    finally:
        out.close()
        if temp.exists():
            temp.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--external-db", type=Path, required=True)
    parser.add_argument("--archive-db", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    args = parser.parse_args()
    print(json.dumps(import_external(args.base, args.external_db, args.archive_db, args.out, args.as_of), indent=2))


if __name__ == "__main__":
    main()
