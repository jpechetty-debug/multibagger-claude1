"""
Peer Comparison Module — DB-Backed
====================================
Compares stocks against sector peers using database-stored metrics.

Sector mapping is loaded dynamically from the multibaggers/microcaps tables
(which already contain sector data from the screener pipeline).
The static SECTOR_MAP is kept as a fallback for symbols not yet in the DB.
"""

import asyncio
import sqlite3
from datetime import datetime
from typing import Any, cast

import pandas as pd

from modules.db_utils import get_db_connection
from modules.fx import to_inr_cr
from modules.retry_utils import run_with_exponential_backoff
from core.observability.logger import get_logger
_log = get_logger("modules.peer_analysis")


# ---------------------------------------------------------------------------
# Sector mapping — dynamic DB lookup with static fallback
# ---------------------------------------------------------------------------

def _load_sector_map_from_db() -> dict[str, str]:
    """Load symbol→sector mapping from multibaggers/microcaps tables."""
    sector_map: dict[str, str] = {}
    try:
        conn = get_db_connection("stocks.db")
        try:
            for table in ("multibaggers", "microcaps"):
                try:
                    cursor = conn.cursor()
                    cursor.execute(
                        f"SELECT symbol, sector FROM {table} WHERE sector IS NOT NULL AND sector != ''"  # noqa: S608
                    )
                    for row in cursor.fetchall():
                        sym = row[0]
                        sect = row[1]
                        if sym and sect:
                            sector_map[sym] = sect
                            # Also store .NS variant
                            if not sym.endswith(".NS"):
                                sector_map[f"{sym}.NS"] = sect
                except sqlite3.OperationalError:
                    pass  # Table may not exist
        finally:
            conn.close()
    except Exception as exc:
        _log.debug("Could not load sector map from DB: %s", exc)
    return sector_map


# Module-level cache — refreshed per session
_DB_SECTOR_MAP: dict[str, str] | None = None


def _get_db_sector_map() -> dict[str, str]:
    global _DB_SECTOR_MAP
    if _DB_SECTOR_MAP is None:
        _DB_SECTOR_MAP = _load_sector_map_from_db()
    return _DB_SECTOR_MAP


# Static fallback for the largest stocks (kept intentionally small — DB is primary)
_STATIC_SECTOR_MAP = {
    # IT
    "TCS.NS": "Information Technology", "INFY.NS": "Information Technology",
    "WIPRO.NS": "Information Technology", "HCLTECH.NS": "Information Technology",
    "TECHM.NS": "Information Technology",
    # Banks
    "HDFCBANK.NS": "Banking & Finance", "ICICIBANK.NS": "Banking & Finance",
    "SBIN.NS": "Banking & Finance", "KOTAKBANK.NS": "Banking & Finance",
    "AXISBANK.NS": "Banking & Finance", "BAJFINANCE.NS": "Banking & Finance",
    # Energy
    "RELIANCE.NS": "Energy", "ONGC.NS": "Energy", "IOC.NS": "Energy",
    "BPCL.NS": "Energy", "NTPC.NS": "Energy",
    # Pharma
    "SUNPHARMA.NS": "Healthcare", "DRREDDY.NS": "Healthcare",
    "CIPLA.NS": "Healthcare", "DIVISLAB.NS": "Healthcare",
    # Auto
    "TATAMOTORS.NS": "Automobile", "M&M.NS": "Automobile",
    "MARUTI.NS": "Automobile", "BAJAJ-AUTO.NS": "Automobile",
    # FMCG
    "HINDUNILVR.NS": "FMCG", "ITC.NS": "FMCG", "NESTLEIND.NS": "FMCG",
    # Metals
    "TATASTEEL.NS": "Metals & Mining", "HINDALCO.NS": "Metals & Mining",
    "JSWSTEEL.NS": "Metals & Mining",
    # Infra/Construction
    "LT.NS": "Infrastructure", "ULTRACEMCO.NS": "Construction Materials",
}


def get_sector(symbol: str) -> str:
    """Get sector for a symbol — DB first, static fallback."""
    # Normalize
    sym = symbol if symbol.endswith((".NS", ".BO")) else f"{symbol}.NS"

    # 1. Try DB
    db_map = _get_db_sector_map()
    sector = db_map.get(sym) or db_map.get(symbol) or db_map.get(symbol.replace(".NS", ""))
    if sector:
        return sector

    # 2. Try static map
    sector = _STATIC_SECTOR_MAP.get(sym)
    if sector:
        return sector

    return "Unknown"


def get_sector_peers(symbol: str, limit: int = 5) -> list[str]:
    """Find peers in the same sector from the DB."""
    sector = get_sector(symbol)
    if sector == "Unknown":
        return []

    peers: list[str] = []
    try:
        db_map = _get_db_sector_map()
        for sym, sect in db_map.items():
            if sect == sector and sym != symbol and sym.endswith(".NS"):
                peers.append(sym)
                if len(peers) >= limit:
                    break
    except Exception:
        pass

    # If DB didn't give enough, fill from static map
    if len(peers) < limit:
        for sym, sect in _STATIC_SECTOR_MAP.items():
            if sect == sector and sym != symbol and sym not in peers:
                peers.append(sym)
                if len(peers) >= limit:
                    break

    return peers[:limit]


def invalidate_sector_cache():
    """Force refresh of sector map on next call."""
    global _DB_SECTOR_MAP
    _DB_SECTOR_MAP = None


# ---------------------------------------------------------------------------
# Stock metrics — DB-backed with yfinance lazy fallback
# ---------------------------------------------------------------------------

def _fetch_metrics_from_db(symbol: str) -> dict | None:
    """Try to get peer metrics from the screener tables."""
    try:
        clean = symbol.replace(".NS", "").replace(".BO", "")
        conn = get_db_connection("stocks.db")
        try:
            cursor = conn.cursor()
            for table in ("multibaggers", "microcaps"):
                try:
                    cursor.execute(
                        f"SELECT * FROM {table} WHERE symbol IN (?, ?) LIMIT 1",  # noqa: S608
                        (symbol, clean),
                    )
                    row = cursor.fetchone()
                    if row:
                        cols = [desc[0] for desc in cursor.description]
                        data = dict(zip(cols, row, strict=False))
                        return _normalize_db_metrics(data, symbol)
                except sqlite3.OperationalError:
                    continue
        finally:
            conn.close()
    except Exception as exc:
        _log.debug("DB metrics lookup failed for %s: %s", symbol, exc)
    return None


def _safe_float(val, default=None):
    if val is None:
        return default
    try:
        result = float(val)
        if result != result:  # NaN
            return default
        return result
    except (ValueError, TypeError):
        return default


def _normalize_db_metrics(data: dict, symbol: str) -> dict:
    """Convert screener table row to peer comparison format."""
    pe = _safe_float(data.get("pe_ratio") or data.get("pe"))
    roe = _safe_float(data.get("roe") or data.get("avg_roe_5y"))
    de = _safe_float(data.get("debt_equity"))
    mcap = _safe_float(data.get("market_cap_cr"))
    price = _safe_float(data.get("price"))
    score = _safe_float(data.get("score"))
    sg = _safe_float(data.get("sales_growth") or data.get("sales_cagr_5y"))
    eps_g = _safe_float(data.get("eps_growth"))

    return {
        "symbol": symbol,
        "name": data.get("company_name") or data.get("name") or symbol.replace(".NS", ""),
        "pe": round(pe, 1) if pe and pe > 0 else None,
        "roe": round(roe, 1) if roe else None,
        "debt_equity": round(de, 2) if de is not None else None,
        "market_cap": int(mcap) if mcap else None,
        "price_change_1m": None,  # Not available from static DB
        "price_change_3m": None,
        "terminal_score": int(score) if score else None,
        "revenue_growth": round(sg, 1) if sg else None,
        "profit_growth": round(eps_g, 1) if eps_g else None,
        "current_price": round(price, 2) if price else None,
    }


async def fetch_stock_metrics(symbol: str) -> dict:
    """
    Fetch peer metrics — DB first, yfinance fallback.
    """
    # 1. Try DB
    db_metrics = await asyncio.to_thread(_fetch_metrics_from_db, symbol)
    if db_metrics and db_metrics.get("pe") is not None:
        return db_metrics

    # 2. yfinance fallback (deprecated)
    _log.warning("DEPRECATION: Using yfinance fallback for peer %s", symbol)
    return await _fetch_metrics_yfinance_fallback(symbol)


async def _fetch_metrics_yfinance_fallback(symbol: str) -> dict:
    """Legacy yfinance peer fetch — kept as fallback only."""
    try:
        import yfinance as yf

        async def _load():
            ticker = await asyncio.to_thread(yf.Ticker, symbol)
            info = await asyncio.to_thread(lambda: ticker.info)
            hist = await asyncio.to_thread(lambda: ticker.history(period="3mo"))
            return ticker, info, hist

        ticker, info, hist = await run_with_exponential_backoff(
            _load,
            context=f"yfinance peer fetch for {symbol}",
        )

        pe = info.get("trailingPE")
        roe = info.get("returnOnEquity")
        if roe:
            roe = round(roe * 100, 1)

        debt_equity = info.get("debtToEquity")
        if debt_equity is not None:
            debt_equity = round(debt_equity / 100, 2)

        market_cap = info.get("marketCap", 0)
        market_cap_cr_raw = to_inr_cr(market_cap, info.get("currency")) if market_cap else None
        market_cap_cr = round(market_cap_cr_raw, 0) if market_cap_cr_raw is not None else None

        current_price = None
        price_change_1m = None
        price_change_3m = None

        if not hist.empty:
            current_price = round(hist["Close"].iloc[-1], 2)
            if len(hist) >= 20:
                price_1m_ago = hist["Close"].iloc[-20]
                price_change_1m = round(((current_price - price_1m_ago) / price_1m_ago) * 100, 1)
            price_3m_ago = hist["Close"].iloc[0]
            price_change_3m = round(((current_price - price_3m_ago) / price_3m_ago) * 100, 1)

        revenue_growth = info.get("revenueGrowth")
        if revenue_growth is not None:
            revenue_growth = round(revenue_growth * 100, 1)
        profit_growth = info.get("earningsGrowth")
        if profit_growth is not None:
            profit_growth = round(profit_growth * 100, 1)

        terminal_score = await get_terminal_score_from_db(symbol)

        return {
            "symbol": symbol,
            "name": info.get("longName", symbol.replace(".NS", "")),
            "pe": round(pe, 1) if pe and pe > 0 else None,
            "roe": roe,
            "debt_equity": debt_equity,
            "market_cap": int(market_cap_cr) if market_cap_cr else None,
            "price_change_1m": price_change_1m,
            "price_change_3m": price_change_3m,
            "terminal_score": terminal_score,
            "revenue_growth": revenue_growth,
            "profit_growth": profit_growth,
            "current_price": current_price,
        }
    except Exception as e:
        _log.error(f"Peer fetch failed for {symbol}: {e}")
        return {"symbol": symbol, "error": str(e)}


# ---------------------------------------------------------------------------
# Comparison entry point
# ---------------------------------------------------------------------------

async def compare_with_peers(symbol: str, peer_symbols: list[str] | None = None):
    """
    Compare a stock with its sector peers.
    """
    sector = get_sector(symbol)
    if peer_symbols is None:
        peer_symbols = get_sector_peers(symbol, limit=5)

    stock_metrics = await fetch_stock_metrics(symbol)

    if not peer_symbols:
        return {
            "stock": symbol,
            "sector": sector,
            "peers": [],
            "stock_metrics": stock_metrics,
            "sector_avg": {},
            "rankings": {"total_peers": 1, "score_rank": 1, "score_rank_desc": "1/1"},
            "timestamp": datetime.now().isoformat(),
        }

    peer_data = await asyncio.gather(
        *[fetch_stock_metrics(peer) for peer in peer_symbols], return_exceptions=True
    )

    clean_peer_data = cast(
        list[dict[str, Any]], [p for p in peer_data if isinstance(p, dict) and "error" not in p]
    )

    all_stocks = [stock_metrics] + clean_peer_data
    sector_avg = calculate_sector_average(all_stocks)
    rankings = calculate_rankings(symbol, all_stocks)

    return {
        "stock": symbol,
        "sector": sector,
        "peers": peer_data,
        "stock_metrics": stock_metrics,
        "sector_avg": sector_avg,
        "rankings": rankings,
        "timestamp": datetime.now().isoformat(),
    }


async def get_terminal_score_from_db(symbol: str) -> int | None:
    """Fetch Terminal Score from stocks.db"""
    try:
        return await asyncio.to_thread(_sync_db_score_lookup, symbol)
    except Exception:
        return None


def _sync_db_score_lookup(symbol: str):
    try:
        with get_db_connection("stocks.db") as conn:
            cursor = conn.cursor()
            clean_symbol = symbol.replace(".NS", "")

            cursor.execute(
                "SELECT score FROM multibaggers WHERE symbol IN (?, ?)", (symbol, clean_symbol)
            )
            row = cursor.fetchone()
            if row:
                return int(row[0])

            cursor.execute("SELECT score FROM microcaps WHERE symbol IN (?, ?)", (symbol, clean_symbol))
            row = cursor.fetchone()
            if row:
                return int(row[0])
    except Exception:
        pass
    return None


def calculate_sector_average(all_stocks: list[dict]) -> dict:
    """Calculate sector average metrics."""
    valid_data = [p for p in all_stocks if "error" not in p]
    if not valid_data:
        return {}

    df = pd.DataFrame(valid_data)
    averages = {}

    cols = ["pe", "roe", "debt_equity", "terminal_score", "revenue_growth", "profit_growth"]
    for col in cols:
        if col in df.columns:
            values = df[col].dropna()
            if not values.empty:
                averages[col] = round(values.mean(), 1)

    return averages


def calculate_rankings(symbol: str, all_stocks: list[dict]) -> dict:
    """Calculate stock ranks among peers."""
    valid_stocks = [s for s in all_stocks if "error" not in s]
    total_peers = len(valid_stocks)

    rankings: dict[str, Any] = {"total_peers": total_peers}

    # PE Ranking (lower is better)
    pe_stocks = sorted(
        [(s["symbol"], s["pe"]) for s in valid_stocks if s.get("pe")], key=lambda x: x[1]
    )
    if pe_stocks:
        rank = next((i + 1 for i, (sym, _) in enumerate(pe_stocks) if sym == symbol), None)
        if rank:
            rankings["pe_rank_desc"] = f"{rank}/{len(pe_stocks)}"
        rankings["pe_rank"] = rank

    # ROE Ranking (higher is better)
    roe_stocks = sorted(
        [(s["symbol"], s["roe"]) for s in valid_stocks if s.get("roe")],
        key=lambda x: x[1],
        reverse=True,
    )
    if roe_stocks:
        rank = next((i + 1 for i, (sym, _) in enumerate(roe_stocks) if sym == symbol), None)
        if rank:
            rankings["roe_rank_desc"] = f"{rank}/{len(roe_stocks)}"
        rankings["roe_rank"] = rank

    # Score Ranking (higher is better)
    score_stocks = sorted(
        [(s["symbol"], s["terminal_score"]) for s in valid_stocks if s.get("terminal_score")],
        key=lambda x: x[1],
        reverse=True,
    )
    if score_stocks:
        rank = next((i + 1 for i, (sym, _) in enumerate(score_stocks) if sym == symbol), None)
        if rank:
            rankings["score_rank_desc"] = f"{rank}/{len(score_stocks)}"
        rankings["score_rank"] = rank

    return rankings
