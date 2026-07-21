#!/usr/bin/env python3
"""
Create a backup artifact in backups/ for CI and first-run deployments.

Usage:
    python scripts/create_backup_artifact.py

Called by:
  - Dockerfile (after DB seed)
  - CI workflow (before test suite)
  - backup.sh / backup.bat post-run
"""
from __future__ import annotations
import shutil
import sqlite3
from pathlib import Path

ROOT    = Path(__file__).resolve().parents[1]
BACKUP  = ROOT / "backups"
BACKUP.mkdir(exist_ok=True)

def _copy_or_create(src: Path, dst: Path, minimal_sql: str) -> None:
    if dst.exists():
        return
    if src.exists():
        shutil.copy2(src, dst)
        print(f"  Copied {src.name} -> backups/ ({dst.stat().st_size:,} bytes)")
    else:
        conn = sqlite3.connect(dst)
        conn.executescript(minimal_sql)
        conn.commit()
        conn.close()
        print(f"  Created minimal {dst.name}")

_copy_or_create(
    ROOT / "runtime" / "stocks.db",
    BACKUP / "stocks.db",
    "CREATE TABLE IF NOT EXISTS multibaggers (symbol TEXT PRIMARY KEY, score REAL);"
    "INSERT OR IGNORE INTO multibaggers VALUES('PLACEHOLDER',0);",
)
_copy_or_create(
    ROOT / "portfolio_history.db",
    BACKUP / "portfolio_history.db",
    "CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, symbol TEXT, status TEXT);",
)

print(f"backups/ ready: {sorted(f.name for f in BACKUP.iterdir())}")
