from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.repository import save_multibaggers


DEFAULT_CSV_PATH = PROJECT_ROOT / "tmp_rs_data.csv"


def _resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path

    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate

    return PROJECT_ROOT / path


def _normalize_key(value: object) -> str:
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def _find_column(columns: list[object], *tokens: str) -> object | None:
    normalized_tokens = tuple(_normalize_key(token) for token in tokens)
    for column in columns:
        normalized = _normalize_key(column)
        if all(token in normalized for token in normalized_tokens):
            return column
    return None


def _load_csv(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)

    header_mask = df.apply(
        lambda row: row.astype(str).str.fullmatch(r"\s*Symbol\s*", case=False, na=False).any(),
        axis=1,
    )
    if header_mask.any():
        header_idx = header_mask[header_mask].index[0]
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx + 1 :].reset_index(drop=True)

    return df


def map_score(signal: object) -> float:
    normalized = str(signal).upper()
    if "STRONG BUY" in normalized:
        return 88.0
    if "BUY" in normalized:
        return 75.0
    if "WATCH" in normalized:
        return 55.0
    if "AVOID" in normalized:
        return 15.0
    return 50.0


def ingest(csv_path: str | Path = DEFAULT_CSV_PATH) -> int:
    resolved_csv_path = _resolve_path(csv_path)
    if not resolved_csv_path.exists():
        print(f"Error: {resolved_csv_path} not found.")
        return 0

    df = _load_csv(resolved_csv_path)
    columns = list(df.columns)

    symbol_col = _find_column(columns, "symbol")
    price_col = _find_column(columns, "price")
    signal_col = _find_column(columns, "signal")
    sector_col = _find_column(columns, "sector")
    rs_col = _find_column(columns, "rs")

    missing = [
        name
        for name, column in (
            ("symbol", symbol_col),
            ("price", price_col),
            ("signal", signal_col),
            ("sector", sector_col),
            ("rs", rs_col),
        )
        if column is None
    ]
    if missing:
        raise ValueError(f"RS CSV is missing required columns: {', '.join(missing)}")

    df = df.rename(
        columns={
            symbol_col: "Symbol",
            price_col: "Price",
            signal_col: "Signal",
            sector_col: "Sector",
            rs_col: "RS%",
        }
    )

    df = df[df["Symbol"].notna()].copy()
    df["Symbol"] = df["Symbol"].astype(str).str.strip()
    df = df[
        (df["Symbol"] != "")
        & (df["Symbol"].str.upper() != "SYMBOL")
        & (df["Symbol"] != "#")
    ].copy()

    df["Symbol"] = df["Symbol"].apply(
        lambda value: value if value.endswith((".NS", ".BO")) else f"{value}.NS"
    )
    df["Price"] = pd.to_numeric(
        df["Price"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(r"[^0-9.\-]", "", regex=True)
        .str.strip(),
        errors="coerce",
    )
    df["Score"] = df["Signal"].apply(map_score)
    df["Rating"] = df["Signal"]
    df["RS_Rating"] = pd.to_numeric(
        df["RS%"]
        .astype(str)
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
        .str.strip(),
        errors="coerce",
    ) * 100

    df_save = df.rename(columns={"Signal": "Technical_Signal"})
    print(f"Ingesting {len(df_save)} signals into database...")
    save_multibaggers(df_save)
    print("Ingestion complete.")
    return len(df_save)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest RS signals from a CSV export.")
    parser.add_argument("--csv-path", default=str(DEFAULT_CSV_PATH), help="Path to the RS CSV export.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ingest(csv_path=args.csv_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
