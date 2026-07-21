# modules/adapters/nse_bhavcopy.py
"""
NSE UDiFF Bhavcopy downloader.
Downloads the daily equity bhavcopy CSV from NSE and parses it into
a symbol-keyed price dictionary for bulk price lookups.
"""
import io
import os
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from core.observability.logger import get_logger

logger = get_logger("adapters.nse_bhavcopy")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CACHE_DIR = _PROJECT_ROOT / "runtime" / "bhavcopy_cache"

# NSE UDiFF URL pattern
_BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/cm/"
    "BhavCopy_NSE_CM_0_0_0_{date}_F_0000.csv.zip"
)

# NSE requires browser-like headers to allow the download
_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.nseindia.com/",
}

# UDiFF column mapping
_COL_MAP = {
    "TckrSymb": "symbol",
    "OpnPric": "open",
    "HghPric": "high",
    "LwPric": "low",
    "ClsPric": "close",
    "TtlTradgVol": "volume",
    "PrvsClsgPric": "prev_close",
    "LastPric": "last_price",
}


def _get_bhavcopy_dates(max_lookback: int = 5) -> list[str]:
    """Return date strings (YYYYMMDD) for today and recent trading days."""
    dates = []
    # Project manifesto requires IST
    dt = datetime.now(ZoneInfo("Asia/Kolkata"))
    while len(dates) < max_lookback:
        # Skip weekends (5=Saturday, 6=Sunday)
        if dt.weekday() < 5:
            dates.append(dt.strftime("%Y%m%d"))
        dt -= timedelta(days=1)
    return dates


def _download_bhavcopy_with_curl_cffi(url: str) -> bytes | None:
    """Download using curl_cffi which handles NSE's TLS fingerprinting."""
    try:
        from curl_cffi import requests as curl_requests
        session = curl_requests.Session(impersonate="chrome")
        # First visit NSE homepage to establish cookies
        session.get("https://www.nseindia.com/", timeout=10)
        resp = session.get(url, headers=_NSE_HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp.content
        logger.debug(f"curl_cffi download returned status {resp.status_code} for {url}")
    except Exception as e:
        logger.debug(f"curl_cffi download failed: {e}")
    return None


def _download_bhavcopy_with_requests(url: str) -> bytes | None:
    """Fallback download using standard requests."""
    try:
        import requests
        session = requests.Session()
        session.get("https://www.nseindia.com/", headers=_NSE_HEADERS, timeout=10)
        resp = session.get(url, headers=_NSE_HEADERS, timeout=30)
        if resp.status_code == 200:
            return resp.content
        logger.debug(f"requests download returned status {resp.status_code} for {url}")
    except Exception as e:
        logger.debug(f"requests download failed: {e}")
    return None


def _parse_bhavcopy_zip(zip_bytes: bytes) -> pd.DataFrame:
    """Extract and parse the CSV from the downloaded ZIP."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            raise ValueError("No CSV found in bhavcopy ZIP")
        with zf.open(csv_names[0]) as csvf:
            df = pd.read_csv(csvf)
    return df


def download_bhavcopy(target_date: str | None = None) -> dict[str, dict]:
    """
    Download and parse NSE UDiFF Bhavcopy.

    Args:
        target_date: Optional YYYYMMDD string. If None, tries today and recent days.

    Returns:
        Dict keyed by NSE symbol (e.g. "RELIANCE") with price data:
        {symbol: {open, high, low, close, volume, prev_close, last_price}}
    """
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    dates_to_try = [target_date] if target_date else _get_bhavcopy_dates()

    for date_str in dates_to_try:
        # Check local cache first
        cache_file = _CACHE_DIR / f"bhavcopy_{date_str}.csv"
        if cache_file.exists():
            logger.info(f"Loading bhavcopy from cache: {cache_file.name}")
            df = pd.read_csv(cache_file)
            return _dataframe_to_price_dict(df)

        url = _BHAVCOPY_URL.format(date=date_str)
        logger.info(f"Downloading bhavcopy for {date_str} from NSE...")

        # Try curl_cffi first (handles Cloudflare), then requests
        zip_bytes = _download_bhavcopy_with_curl_cffi(url)
        if zip_bytes is None:
            zip_bytes = _download_bhavcopy_with_requests(url)

        if zip_bytes is not None:
            try:
                df = _parse_bhavcopy_zip(zip_bytes)
                # Cache the raw CSV for the day
                df.to_csv(cache_file, index=False)
                logger.info(f"Bhavcopy downloaded: {len(df)} rows for {date_str}")
                return _dataframe_to_price_dict(df)
            except Exception as e:
                logger.warning(f"Failed to parse bhavcopy for {date_str}: {e}")
                continue
        else:
            logger.debug(f"No bhavcopy available for {date_str}")

    logger.warning("Could not download bhavcopy for any recent date")
    return {}


def _dataframe_to_price_dict(df: pd.DataFrame) -> dict[str, dict]:
    """Convert bhavcopy DataFrame to {symbol: price_data} dict."""
    result = {}

    # Find available columns (UDiFF format)
    available_cols = {col: _COL_MAP[col] for col in _COL_MAP if col in df.columns}

    if "TckrSymb" not in available_cols:
        # Try alternate column names
        if "SYMBOL" in df.columns:
            available_cols["SYMBOL"] = "symbol"
        else:
            logger.warning(f"Bhavcopy missing symbol column. Columns: {list(df.columns)}")
            return {}

    # Filter for Equity (EQ) and Book Entry (BE) series only if the column exists
    if "SctySrs" in df.columns:
        df = df[df["SctySrs"].isin(("EQ", "BE"))]
    elif "SERIES" in df.columns:
        df = df[df["SERIES"].isin(("EQ", "BE"))]

    sym_col = next(k for k, v in available_cols.items() if v == "symbol")

    for _, row in df.iterrows():
        symbol = str(row[sym_col]).strip()
        if not symbol:
            continue

        price_data = {}
        for raw_col, mapped_name in available_cols.items():
            if mapped_name == "symbol":
                continue
            val = row.get(raw_col)
            if pd.notna(val):
                try:
                    price_data[mapped_name] = float(val)
                except (TypeError, ValueError):
                    pass

        if price_data.get("close") or price_data.get("last_price"):
            result[symbol] = price_data
            # Also store with .NS suffix for direct yfinance-style lookup
            result[f"{symbol}.NS"] = price_data

    return result


def get_bhavcopy_price(prices: dict[str, dict], symbol: str) -> float | None:
    """Get closing price for a symbol from bhavcopy data."""
    data = (
        prices.get(symbol) 
        or prices.get(symbol.replace(".NS", "")) 
        or prices.get(f"{symbol.replace('.NS', '')}.NS")
    )
    if data:
        return data.get("close") or data.get("last_price")
    return None
