"""Fetch NSE listing/delisting metadata for survivorship-aware backtests.

Writes data/nse_listing_dates.csv with columns:
Symbol, Listing_Date, Delisting_Date
"""

from __future__ import annotations

import argparse
import re
import sys
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "nse_listing_dates.csv"
SECURITIES_PAGE_URL = "https://www.nseindia.com/static/market-data/securities-available-for-trading"
EQUITY_CSV_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
DELISTING_PAGE_URL = "https://www.nseindia.com/static/list/list-of-companies-proposed-to-be-delisted"
DEFAULT_DELISTED_LISTING_DATE = "1900-01-01"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Manual overrides for suspended/delisted symbols that still appear in active list or are missing in delisted XLSX.
MANUAL_DELISTING_OVERRIDES = {
    "RCOM": "2021-04-29",
}



def _download(session: requests.Session, url: str) -> bytes:
    response = session.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    return response.content


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [re.sub(r"\s+", " ", str(col)).strip().upper() for col in out.columns]
    return out


def _find_column(columns: list[str], *needles: str) -> str | None:
    normalized_needles = [needle.upper() for needle in needles]
    for column in columns:
        compact = re.sub(r"[^A-Z0-9]", "", column.upper())
        for needle in normalized_needles:
            if re.sub(r"[^A-Z0-9]", "", needle) in compact:
                return column
    return None


def _normalize_date(value, default: str = "") -> str:
    if value is None or str(value).strip().lower() in {"", "nan", "nat", "none", "null"}:
        return default
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return default
    return parsed.date().isoformat()


def _load_active_equity(session: requests.Session, url: str) -> pd.DataFrame:
    df = pd.read_csv(BytesIO(_download(session, url)))
    df = _normalize_columns(df)
    symbol_col = _find_column(list(df.columns), "SYMBOL")
    listing_col = _find_column(list(df.columns), "DATE OF LISTING", "LISTING DATE")
    if symbol_col is None or listing_col is None:
        raise RuntimeError(
            f"Could not find Symbol/Listing Date columns in active NSE CSV: {list(df.columns)}"
        )
    out = pd.DataFrame(
        {
            "Symbol": df[symbol_col].astype(str).str.strip().str.upper(),
            "Listing_Date": df[listing_col].apply(_normalize_date),
            "Delisting_Date": "",
        }
    )
    return out[(out["Symbol"] != "") & (out["Listing_Date"] != "")]


def _discover_delisted_url(session: requests.Session, page_url: str) -> str | None:
    html = _download(session, page_url).decode("utf-8", errors="ignore")
    match = re.search(
        r'href="([^"]+\.xlsx[^"]*)">[^<]*List of Companies Delisted from NSE',
        html,
        flags=re.IGNORECASE,
    )
    if match:
        return urljoin(page_url, match.group(1))

    for href in re.findall(r'href="([^"]+\.xlsx[^"]*)"', html, flags=re.IGNORECASE):
        if "delist" in href.lower():
            return urljoin(page_url, href)
    return None


def _load_delisted_equity(
    session: requests.Session,
    url: str,
    default_listing_date: str,
) -> pd.DataFrame:
    xls = pd.ExcelFile(BytesIO(_download(session, url)))
    sheets_dfs = []
    for sheet_name in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sheet_name)
        df = _normalize_columns(df).dropna(how="all")
        symbol_col = _find_column(list(df.columns), "SYMBOL")
        delisting_col = _find_column(list(df.columns), "DELISTING DATE", "DATE OF DELISTING", "DELISTED DATE")
        if symbol_col is None or delisting_col is None:
            continue

        listing_col = _find_column(list(df.columns), "LISTING DATE", "DATE OF LISTING")
        listing_values = (
            df[listing_col].apply(lambda value: _normalize_date(value, default_listing_date))
            if listing_col is not None
            else pd.Series([default_listing_date] * len(df), index=df.index)
        )
        out = pd.DataFrame(
            {
                "Symbol": df[symbol_col].astype(str).str.strip().str.upper(),
                "Listing_Date": listing_values,
                "Delisting_Date": df[delisting_col].apply(_normalize_date),
            }
        )
        sheets_dfs.append(out[(out["Symbol"] != "") & (out["Delisting_Date"] != "")])

    if not sheets_dfs:
        raise RuntimeError(
            f"Could not find Symbol/Delisting Date columns in any sheets of NSE delisted file: {xls.sheet_names}"
        )
    return pd.concat(sheets_dfs, ignore_index=True)


def build_listing_metadata(args: argparse.Namespace) -> pd.DataFrame:
    session = requests.Session()
    # Prime NSE cookies before archive downloads; harmless if the static page is cached.
    try:
        session.get(args.securities_page_url, headers=HEADERS, timeout=20)
    except requests.RequestException:
        pass

    active = _load_active_equity(session, args.active_url)
    frames = [active]

    if not args.skip_delisted:
        delisted_url = args.delisted_url or _discover_delisted_url(session, args.delisted_page_url)
        if delisted_url:
            try:
                frames.append(
                    _load_delisted_equity(
                        session,
                        delisted_url,
                        args.default_delisted_listing_date,
                    )
                )
            except ImportError as exc:
                print(
                    f"warning: could not read delisted XLSX ({exc}); install openpyxl.",
                    file=sys.stderr,
                )
            except Exception as exc:
                print(f"warning: skipped delisted file {delisted_url}: {exc}", file=sys.stderr)
        else:
            print("warning: could not discover NSE delisted companies XLSX", file=sys.stderr)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset=["Symbol"], keep="last")
    
    # Apply manual overrides for delisted/suspended symbols
    for symbol, delist_date in MANUAL_DELISTING_OVERRIDES.items():
        mask = combined["Symbol"] == symbol
        if mask.any():
            combined.loc[mask, "Delisting_Date"] = delist_date

    combined = combined.sort_values("Symbol").reset_index(drop=True)
    return combined[["Symbol", "Listing_Date", "Delisting_Date"]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--active-url", default=EQUITY_CSV_URL)
    parser.add_argument("--securities-page-url", default=SECURITIES_PAGE_URL)
    parser.add_argument("--delisted-page-url", default=DELISTING_PAGE_URL)
    parser.add_argument("--delisted-url", default="")
    parser.add_argument("--skip-delisted", action="store_true")
    parser.add_argument(
        "--default-delisted-listing-date",
        default=DEFAULT_DELISTED_LISTING_DATE,
        help="Fallback listing date when NSE's delisted workbook lacks one.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata = build_listing_metadata(args)
    metadata.to_csv(output, index=False)
    active_count = int(metadata["Delisting_Date"].eq("").sum())
    delisted_count = int(metadata["Delisting_Date"].ne("").sum())
    print(
        f"Wrote {len(metadata)} NSE listing records to {output} "
        f"({active_count} active, {delisted_count} delisted)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
