"""
Targeted CFO/PAT and Debt/Equity backfill of stored picks.

Background: the Screener.in CFO parser was broken (fixed in 7699b71), so most
rows in `multibaggers` carry cfo_pat_ratio = 0, which trips the Cash Quality
ceiling. This script re-fetches ONLY the Screener.in page for those rows
(one request each, rate-limited by the provider), stores the real ratio or
NULL.

It does NOT rescore. Rescoring stored rows is not equivalent to a scan: rows lack
the sector medians, sector-rotation boost and earnings-inflection score the scan
uses (SANDUMA rescored to 79.7 vs 100 in the scan). Refresh scores with a full
scan: powershell -File scripts/run_scan.ps1

Debt/Equity had the same missing-as-zero problem (Screener.in supplied no D/E,
and the yfinance fallback defaulted to 0, which scores as debt-free), so rows
with debt_equity = 0 are refetched in the same pass. Each field is only
overwritten on the rows where it was 0.

Resumable: phase 1 only selects rows still at exactly 0, so an interrupted run
picks up where it stopped (genuinely debt-free rows stay at 0 and are refetched). A copy of the DB is taken before the first write.

Usage:
    python scripts/internal/backfill_cfo.py                # backfill
    python scripts/internal/backfill_cfo.py --limit 20     # try a small batch first
    python scripts/internal/backfill_cfo.py --dry-run      # fetch and print, write nothing
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.adapters.screener_in import ScreenerInProvider  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / "runtime" / "stocks.db"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _backup(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"{db_path.stem}_before_cfo_backfill_{datetime.now():%Y%m%d_%H%M%S}.db"
    shutil.copy2(db_path, dest)
    return dest


def backfill_cfo(conn: sqlite3.Connection, limit: int | None, dry_run: bool) -> tuple[int, int]:
    rows = conn.execute(
        "SELECT symbol, cfo_pat_ratio = 0 AS need_cfo, debt_equity = 0 AS need_de "
        "FROM multibaggers WHERE cfo_pat_ratio = 0 OR debt_equity = 0 ORDER BY symbol"
    ).fetchall()
    if limit:
        rows = rows[:limit]
    print(f"Phase 1: fetching CFO/PAT and D/E for {len(rows)} stocks (~2s each)")

    provider = ScreenerInProvider()
    found = missing = 0
    started = time.monotonic()
    for i, row in enumerate(rows, start=1):
        symbol = row["symbol"]
        try:
            data = asyncio.run(provider.fetch_fundamentals(symbol))
        except Exception as exc:  # network/parse failure: leave row at 0 so a rerun retries it
            print(f"  [{i}/{len(rows)}] {symbol}: fetch failed ({exc}); will retry next run")
            continue
        updates = {}
        if row["need_cfo"]:
            updates["cfo_pat_ratio"] = data.get("CFO_PAT_Ratio")
        if row["need_de"]:
            updates["debt_equity"] = data.get("Debt_Equity")
        for value in updates.values():
            if value is None:
                missing += 1
            else:
                found += 1
        if dry_run:
            print(f"  {symbol}: {updates}")
        else:
            assignments = ", ".join(f"{col} = ?" for col in updates)
            conn.execute(f"UPDATE multibaggers SET {assignments} WHERE symbol = ?", (*updates.values(), symbol))
            conn.commit()
        if i % 25 == 0 or i == len(rows):
            eta = (time.monotonic() - started) / i * (len(rows) - i)
            print(f"  [{i}/{len(rows)}] found={found} missing={missing} eta={eta / 60:.1f} min")
    return found, missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--limit", type=int, default=None, help="only fetch the first N stocks")
    parser.add_argument("--dry-run", action="store_true", help="fetch and print but write nothing")
    args = parser.parse_args()

    logging.disable(logging.WARNING)
    if not args.db.exists():
        print(f"DB not found: {args.db}")
        return 1
    if not args.dry_run:
        print(f"Backup: {_backup(args.db)}")

    conn = _connect(args.db)
    try:
        found, missing = backfill_cfo(conn, args.limit, args.dry_run)
        print(f"Done: {found} values found, {missing} unavailable (stored as NULL)")
        print("Scores are unchanged; run a full scan to refresh them: powershell -File scripts/run_scan.ps1")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
