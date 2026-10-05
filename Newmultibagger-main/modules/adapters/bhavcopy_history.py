# modules/adapters/bhavcopy_history.py
"""
Daily OHLCV price history built from cached NSE UDiFF bhavcopy files.

Replaces yfinance ``Ticker.history()`` for NSE equities:

* ``update_cache(days)`` downloads each missing NSE trading day once (cookie-free
  public archive) and stores a slim equity-only CSV per day.
* ``get_history(symbol, period)`` returns a yfinance-shaped frame
  (Open/High/Low/Close/Volume, DatetimeIndex) read purely from the cache — no
  network — or an empty frame when the cache can't cover the request, so callers
  can fall back.

Corporate actions: bhavcopy prices are unadjusted, but on an ex-date NSE reports
the *adjusted* previous close (``PrvsClsgPric``). The ratio
``prev_close[t] / close[t-1]`` therefore reveals each split/bonus, and all earlier
prices are scaled by it (volume inversely) — the same back-adjustment yfinance
applies. Regular dividends don't change ``PrvsClsgPric`` and are not adjusted.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from core.observability.logger import get_logger
from modules.adapters.nse_bhavcopy import _BHAVCOPY_URL, _NSE_HEADERS, _parse_bhavcopy_zip

logger = get_logger("adapters.bhavcopy_history")

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
HISTORY_DIR = _PROJECT_ROOT / "runtime" / "bhavcopy_history"

EQUITY_SERIES = ("EQ", "BE", "SM", "ST", "BZ", "E1")
_KEEP = {
    "TckrSymb": "symbol",
    "SctySrs": "series",
    "OpnPric": "Open",
    "HghPric": "High",
    "LwPric": "Low",
    "ClsPric": "Close",
    "PrvsClsgPric": "PrevClose",
    "TtlTradgVol": "Volume",
}
PERIOD_DAYS = {"5d": 7, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731, "5y": 1827}
# Ratio deviation that counts as a corporate action rather than price rounding.
ADJUST_TOLERANCE = 0.005
# Cache is unusable for "current" analysis if its last day lags the last trading day by more.
MAX_STALE_TRADING_DAYS = 3

# If more than this share of symbols "adjust" on one date, it's a data gap, not a split.
MARKET_WIDE_GAP_SHARE = 0.02

_panel_lock = threading.Lock()
_panel: pd.DataFrame | None = None
_panel_files: frozenset[str] = frozenset()
_gap_dates: frozenset[pd.Timestamp] = frozenset()


def _today_ist() -> date:
    return datetime.now(ZoneInfo("Asia/Kolkata")).date()


def _trading_days(start: date, end: date) -> list[date]:
    from modules.data_layer.data_utils import get_valid_trading_days

    return list(get_valid_trading_days(start.isoformat(), end.isoformat()))


def _day_file(d: date) -> Path:
    return HISTORY_DIR / f"eq_{d:%Y%m%d}.csv"


def _missing_marker(d: date) -> Path:
    return HISTORY_DIR / f"eq_{d:%Y%m%d}.missing"


def _slim(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in _KEEP if c in df.columns]
    out = df[cols].rename(columns=_KEEP)
    out = out[out["series"].isin(EQUITY_SERIES)]
    return out


def _download_day(session, d: date) -> str:
    url = _BHAVCOPY_URL.format(date=f"{d:%Y%m%d}")
    try:
        resp = session.get(url, headers=_NSE_HEADERS, timeout=30)
    except Exception as exc:  # transient — retried on the next update
        return f"error: {exc}"
    if resp.status_code == 404:
        # Published files never 404; mark only settled past days so today's
        # not-yet-published file is retried later.
        if d < _today_ist() - timedelta(days=2):
            _missing_marker(d).touch()
        return "missing"
    if resp.status_code != 200:
        return f"error: HTTP {resp.status_code}"
    try:
        _slim(_parse_bhavcopy_zip(resp.content)).to_csv(_day_file(d), index=False)
    except Exception as exc:
        return f"error: parse {exc}"
    return "ok"


def update_cache(days: int = 400, workers: int = 4) -> dict[str, int]:
    """Download every day in the last ``days`` calendar days not yet cached.

    Every calendar day is tried, not just the exchange calendar's trading days:
    NSE holds special sessions the calendar omits (Diwali Muhurat trading,
    Sunday Budget sessions), and the day after such a session reports its close
    as PrvsClsgPric. Missing it makes that ordinary price move look like a
    market-wide corporate action. Non-trading days 404 once and are marked.
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    end = _today_ist()
    start = end - timedelta(days=days)
    wanted = [
        start + timedelta(days=i) for i in range((end - start).days + 1)
        if not _day_file(start + timedelta(days=i)).exists()
        and not _missing_marker(start + timedelta(days=i)).exists()
    ]
    stats = {"wanted": len(wanted), "ok": 0, "missing": 0, "error": 0}
    if not wanted:
        return stats

    from curl_cffi import requests as curl_requests

    def worker(chunk: list[date]) -> list[str]:
        session = curl_requests.Session(impersonate="chrome")
        try:
            session.get("https://www.nseindia.com/", headers=_NSE_HEADERS, timeout=15)
        except Exception as exc:
            logger.warning(f"bhavcopy_history: NSE warm-up failed: {exc}")
        return [_download_day(session, d) for d in chunk]

    chunks = [wanted[i::workers] for i in range(workers)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for results in pool.map(worker, chunks):
            for r in results:
                stats["ok" if r == "ok" else "missing" if r == "missing" else "error"] += 1
    logger.info(f"bhavcopy_history: cache update {stats}")
    return stats


def _load_panel() -> pd.DataFrame:
    """All cached days as one frame (symbol, Date, OHLCV, PrevClose); reloads when files change."""
    global _panel, _panel_files, _gap_dates
    files = frozenset(p.name for p in HISTORY_DIR.glob("eq_*.csv")) if HISTORY_DIR.exists() else frozenset()
    with _panel_lock:
        if _panel is not None and files == _panel_files:
            return _panel
        frames = []
        for name in sorted(files):
            day = pd.read_csv(HISTORY_DIR / name)
            day["Date"] = pd.Timestamp(datetime.strptime(name[3:11], "%Y%m%d"))
            frames.append(day)
        panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        if not panel.empty:
            panel = panel[panel["series"].isin(EQUITY_SERIES)]
            # A symbol occasionally trades in two series on one day; keep EQ first.
            panel["_rank"] = (panel["series"] != "EQ").astype(int)
            panel = (
                panel.sort_values(["symbol", "Date", "_rank"])
                .drop_duplicates(["symbol", "Date"])
                .drop(columns=["_rank", "series"])
            )
        _gap_dates = _find_gap_dates(panel)
        if _gap_dates:
            logger.warning(
                "bhavcopy_history: ignoring prev-close jumps on data-gap dates "
                f"{sorted(str(d.date()) for d in _gap_dates)} — a session file is missing"
            )
        _panel, _panel_files = panel, files
        return panel


def _find_gap_dates(panel: pd.DataFrame) -> frozenset[pd.Timestamp]:
    if panel.empty:
        return frozenset()
    prev = panel.groupby("symbol")["Close"].shift(1)
    jumped = ((panel["PrevClose"] / prev) - 1).abs() > ADJUST_TOLERANCE
    share = jumped.groupby(panel["Date"]).mean()
    return frozenset(share[share > MARKET_WIDE_GAP_SHARE].index)


def _back_adjust(df: pd.DataFrame, ignore_dates: frozenset = frozenset()) -> pd.DataFrame:
    """Scale prices before each split/bonus ex-date so the series is continuous."""
    ratio = df["PrevClose"] / df["Close"].shift(1)
    ratio = ratio.where((ratio - 1).abs() > ADJUST_TOLERANCE, 1.0).fillna(1.0)
    if ignore_dates:
        ratio[df.index.isin(list(ignore_dates))] = 1.0
    # Factor for day t = product of ratios on all later days.
    factor = ratio[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    out = df.copy()
    for col in ("Open", "High", "Low", "Close"):
        out[col] = out[col] * factor
    out["Volume"] = out["Volume"] / factor
    return out


def get_history(symbol: str, period: str = "1y") -> pd.DataFrame:
    """yfinance-shaped daily history for an NSE symbol from the local cache.

    Returns an empty frame (caller should fall back) when the symbol is not an
    NSE equity, the cache doesn't reach back far enough, or it is stale.
    """
    if symbol.endswith(".BO") or symbol.startswith("^"):
        return pd.DataFrame()
    panel = _load_panel()
    if panel.empty:
        return pd.DataFrame()

    today = _today_ist()
    recent = _trading_days(today - timedelta(days=14), today)
    last_cached = panel["Date"].max().date()
    lag = sum(1 for d in recent if d > last_cached and d < today)
    if lag > MAX_STALE_TRADING_DAYS:
        logger.warning(f"bhavcopy_history: cache stale ({last_cached}); run update_cache()")
        return pd.DataFrame()

    days = PERIOD_DAYS.get(period, 366)
    start = pd.Timestamp(today - timedelta(days=days))
    if panel["Date"].min() > start + pd.Timedelta(days=10):
        return pd.DataFrame()  # cache doesn't cover the requested window

    clean = symbol.upper().removesuffix(".NS")
    rows = panel[panel["symbol"] == clean].set_index("Date").sort_index()
    if rows.empty:
        return pd.DataFrame()
    adjusted = _back_adjust(rows, _gap_dates)
    out = adjusted.loc[adjusted.index >= start, ["Open", "High", "Low", "Close", "Volume"]]
    out.attrs["source"] = "nse_bhavcopy"
    return out
