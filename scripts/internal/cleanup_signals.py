from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "stocks.db"


def _resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path

    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate

    return PROJECT_ROOT / path


def cleanup_symbols(symbols: list[str], db_path: str | Path = DEFAULT_DB_PATH) -> int:
    normalized_symbols = [symbol.strip() for symbol in symbols if symbol and symbol.strip()]
    if not normalized_symbols:
        print("No symbols provided for cleanup.")
        return 0

    resolved_db_path = _resolve_path(db_path)
    print(f"Checking database at {resolved_db_path.resolve()}")

    conn = sqlite3.connect(resolved_db_path)
    cursor = conn.cursor()

    placeholders = ", ".join("?" for _ in normalized_symbols)
    deleted_rows = 0

    for table in ("multibaggers", "fundamentals_pit"):
        try:
            cursor.execute(
                f"DELETE FROM {table} WHERE symbol IN ({placeholders})",
                normalized_symbols,
            )
            table_deleted = cursor.rowcount if cursor.rowcount != -1 else 0
            deleted_rows += table_deleted
            print(f"Deleted {table_deleted} rows from {table}.")
        except sqlite3.OperationalError as exc:
            print(f"Skipped {table}: {exc}")

    conn.commit()
    conn.close()
    print(f"Cleanup complete for symbols: {', '.join(normalized_symbols)}")
    return deleted_rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Delete RS signal records for specific symbols.")
    parser.add_argument("--symbols", nargs="+", required=True, help="Symbols to delete from RS tables.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cleanup_symbols(symbols=args.symbols, db_path=args.db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
