"""
app_routes/liquidity_sim.py
============================
Sovereign AI — Live Liquidity Simulator Endpoint

GET /api/liquidity-sim/{symbol}?position_cr=X

Returns a full slippage + position-sizing simulation for a given symbol
and intended position size (₹ Crore).  Unlike the static /api/liquidity
forensics dump, this endpoint:

  1. Fetches live stock data from the multibaggers table (or falls back
     to a live yfinance call if not in DB).
  2. Runs simulate_liquidity() from modules.liquidity.
  3. Returns the rich LiquiditySimResult JSON payload.

Designed to be called from the frontend position-sizing calculator.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import text

from db.db_core import get_db_connection as get_sqla_connection
from modules.connections import _run_blocking
from modules.fx import to_inr_cr
from modules.liquidity import simulate_liquidity
from modules.rate_limit import limiter
from modules.symbol_utils import canonical_symbol

router = APIRouter()

# ── Symbol validation ──────────────────────────────────────────────────────

import re
_SYMBOL_RE = re.compile(r"^[A-Z0-9&]{1,20}(\.(NS|BO|BSE))?$", re.IGNORECASE)


def _validate_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(status_code=422, detail=f"Invalid symbol: {symbol!r}")
    return s


# ── Data helpers ───────────────────────────────────────────────────────────

def _fetch_from_db(symbol: str) -> dict | None:
    """
    Try to load stock data from the multibaggers table.
    Returns None if symbol not found.
    """
    try:
        with get_sqla_connection() as conn:
            df = pd.read_sql(
                text("SELECT * FROM multibaggers WHERE symbol = :sym"),
                conn,
                params={"sym": symbol},
            )
        if df.empty:
            return None
        row = df.iloc[0].to_dict()
        # Normalise field names to match simulate_liquidity expectations
        return {
            "Symbol": row.get("symbol", symbol),
            "Price": row.get("price"),
            "Avg_Volume_10D": row.get("avg_volume_10d") or row.get("volume"),
            "ATR": row.get("atr"),
            "Market_Cap_Cr": row.get("market_cap_cr"),
        }
    except Exception:
        return None


def _fetch_from_yfinance(yf_symbol: str) -> dict:
    """
    Live fallback: pull 20-day OHLCV from yfinance and compute
    10-day average volume, current price, and ATR.
    """
    import yfinance as yf

    ticker = yf.Ticker(yf_symbol)
    hist = ticker.history(period="20d")

    if hist.empty:
        raise HTTPException(
            status_code=404,
            detail=f"No price data found for {yf_symbol}. "
                   "Check the symbol or add exchange suffix (.NS / .BO).",
        )

    price = float(hist["Close"].iloc[-1])
    avg_vol_10d = float(hist["Volume"].tail(10).mean())

    # ATR (14-day, capped to available data)
    high = hist["High"]
    low = hist["Low"]
    close_prev = hist["Close"].shift(1)
    tr = pd.concat(
        [high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1
    ).max(axis=1)
    atr = float(tr.tail(14).mean()) if len(tr) >= 5 else None

    # Market cap from info (best-effort)
    try:
        info = ticker.info
        mktcap_cr = (
            to_inr_cr(info.get("marketCap"), info.get("currency")) if info.get("marketCap") else None
        )
    except Exception:
        mktcap_cr = None

    return {
        "Symbol": yf_symbol,
        "Price": price,
        "Avg_Volume_10D": avg_vol_10d,
        "ATR": atr,
        "Market_Cap_Cr": mktcap_cr,
    }


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.get("/api/liquidity-sim/{symbol}")
@limiter.limit("20/minute")
async def liquidity_simulator(
    request: Request,
    symbol: str,
    position_cr: float = Query(
        ...,
        gt=0,
        le=10000,
        description="Intended position size in Indian Rupees Crore (₹ Cr). "
                    "Example: position_cr=5 means ₹5 Crore.",
    ),
):
    """
    Live Liquidity Simulator.

    Estimates market impact, slippage, days-to-build, and days-to-exit
    for a given position size in a specific stock.

    ### Parameters
    - **symbol**: NSE/BSE ticker (e.g. `RELIANCE`, `RELIANCE.NS`, `SBIN.BO`)
    - **position_cr**: Intended position size in ₹ Crore

    ### Returns
    Full simulation payload including:
    - `liquidity.advt_cr` — Average Daily Value Traded
    - `liquidity.score` — 0-100 liquidity score
    - `position_sizing.days_to_build` — sessions to accumulate
    - `position_sizing.days_to_exit` — sessions to fully exit
    - `slippage.entry_pct` — estimated entry market impact
    - `slippage.roundtrip_pct` — round-trip cost
    - `sizing_recommendation.recommended_position_cr` — max size for < 0.5% slippage
    - `risk.verdict` — GREEN / AMBER / RED
    - `risk.flags` — list of warning messages
    """
    raw_symbol = _validate_symbol(symbol)
    yf_symbol = canonical_symbol(raw_symbol)

    def _run():
        # 1. Try DB first (fast, no rate-limit concern)
        stock_data = _fetch_from_db(raw_symbol) or _fetch_from_db(yf_symbol)

        # 2. Fall back to live yfinance if not in DB
        if not stock_data:
            stock_data = _fetch_from_yfinance(yf_symbol)

        return simulate_liquidity(stock_data, position_cr)

    try:
        result = await _run_blocking(_run)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Liquidity simulation failed: {exc}"
        ) from exc

    return {
        **result.to_dict(),
        "meta": {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "yf_symbol": yf_symbol,
            "position_cr_requested": position_cr,
        },
    }
