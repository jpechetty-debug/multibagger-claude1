# scripts/backup_restore.py
"""
Sovereign AI — DB Backup & Restore Utility

Usage:
  python scripts/backup_restore.py backup              # Create a timestamped backup
  python scripts/backup_restore.py restore <path>      # Restore from a backup file
  python scripts/backup_restore.py list                 # List available backups
  python scripts/backup_restore.py prune --keep 5       # Keep only N most recent backups
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
DB_PATH = RUNTIME_DIR / "stocks.db"
BACKUP_DIR = PROJECT_ROOT / "backups"
DEFAULT_KEEP = 5


def backup() -> Path:
    """Create a timestamped backup of the runtime DB."""
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        sys.exit(1)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"stocks_{timestamp}.db"

    # Use SQLite backup API for consistency
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(backup_path))
    try:
        src.backup(dst)
        print(f"OK: Backup created at {backup_path}")
        print(f"    Size: {backup_path.stat().st_size / 1024:.1f} KB")
        return backup_path
    finally:
        dst.close()
        src.close()


def restore(backup_file: str) -> None:
    """Restore a backup file to the runtime DB."""
    src_path = Path(backup_file)
    if not src_path.exists():
        # Try looking in backups dir
        src_path = BACKUP_DIR / backup_file
    if not src_path.exists():
        print(f"ERROR: Backup file not found: {backup_file}")
        sys.exit(1)

    # Validate backup integrity
    try:
        conn = sqlite3.connect(str(src_path))
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        if result[0] != "ok":
            print(f"ERROR: Backup file failed integrity check: {result[0]}")
            sys.exit(1)
    except Exception as exc:
        print(f"ERROR: Cannot open backup file: {exc}")
        sys.exit(1)

    # Create a safety backup of current DB before restoring
    if DB_PATH.exists():
        safety = DB_PATH.with_suffix(".db.pre-restore")
        shutil.copy2(str(DB_PATH), str(safety))
        print(f"    Safety copy of current DB saved to {safety}")

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src_path), str(DB_PATH))
    print(f"OK: Restored {src_path.name} → {DB_PATH}")


def list_backups() -> list[Path]:
    """List all available backups sorted by date."""
    if not BACKUP_DIR.exists():
        print("No backups directory found.")
        return []

    backups = sorted(BACKUP_DIR.glob("stocks_*.db"), reverse=True)
    if not backups:
        print("No backups found.")
        return []

    print(f"{'Name':<30} {'Size':<12} {'Created'}")
    print("-" * 60)
    for b in backups:
        size_kb = b.stat().st_size / 1024
        modified = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"{b.name:<30} {size_kb:>8.1f} KB  {modified}")

    return backups


def prune(keep: int = DEFAULT_KEEP) -> None:
    """Remove old backups, keeping only the N most recent."""
    if not BACKUP_DIR.exists():
        return

    backups = sorted(BACKUP_DIR.glob("stocks_*.db"), reverse=True)
    to_remove = backups[keep:]

    if not to_remove:
        print(f"OK: {len(backups)} backups found, all within retention ({keep}).")
        return

    for b in to_remove:
        b.unlink()
        print(f"    Pruned: {b.name}")

    print(f"OK: Removed {len(to_remove)} old backups. Kept {keep}.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Sovereign DB Backup & Restore")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("backup", help="Create a timestamped backup")
    restore_cmd = sub.add_parser("restore", help="Restore from a backup file")
    restore_cmd.add_argument("path", help="Path to backup file")
    sub.add_parser("list", help="List available backups")
    prune_cmd = sub.add_parser("prune", help="Prune old backups")
    prune_cmd.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="Number of backups to keep")

    args = parser.parse_args()

    if args.command == "backup":
        backup()
    elif args.command == "restore":
        restore(args.path)
    elif args.command == "list":
        list_backups()
    elif args.command == "prune":
        prune(args.keep)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
