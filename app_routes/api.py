from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
import pandas as pd
import numpy as np
import json
import os
import csv
import asyncio
import yfinance as yf
import time
from datetime import datetime
from pydantic import BaseModel, Field

from fastapi.responses import FileResponse
import modules.dependencies as deps
from modules.retry_utils import run_with_exponential_backoff
from app_routes.contracts import RegimeStatusResponse
from modules.symbol_utils import normalize_symbol
from modules.revisions import analyze_revisions
from modules.drift_monitor import monitor_drift
from modules.allocation_hrp import HRPAllocator

router = APIRouter()

@router.websocket("/ws/signals")
async def websocket_endpoint(websocket: WebSocket):
    await deps.manager.connect(websocket)
    try:
        while True:
            # Keep the connection open and handle potential pings
            await websocket.receive_text()
    except WebSocketDisconnect:
        deps.manager.disconnect(websocket)
    except Exception:
        deps.manager.disconnect(websocket)




@router.get("/api/stocks")
async def get_multibaggers(as_of_date: str | None = None):
    """Fetch Top Multibagger Picks"""
    try:
        if as_of_date:
            from db.repository import load_fundamentals_universe_as_of

            def _read_as_of_records():
                df, snapshot_date = load_fundamentals_universe_as_of(
                    as_of_date
                )
                if df.empty:
                    return []
                df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
                records = df.to_dict(orient="records")
                for record in records:
                    if not record.get("as_of_date"):
                        record["as_of_date"] = snapshot_date
                return records

            return await deps._run_blocking(_read_as_of_records)

        # 1. Fetch Multibaggers (Phase 6: Deterministic Tie-Breaker Sorting)
        records = await deps._run_blocking(
            deps._read_records, "SELECT * FROM multibaggers ORDER BY score DESC, rs_rating DESC, market_cap_cr DESC"
        )

        if not records:
            return []

        return deps._json_safe_clean(records)
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/multibagger-hunt")
async def get_multibagger_hunt():
    """Fetch stocks meeting the strict Multibagger Hunt criteria"""
    try:
        # Framework Filters from ticker_list.py
        query = """
            SELECT * FROM multibaggers
            WHERE sales_cagr_5y >= 0.15
              AND avg_roe_5y >= 0.15
              AND debt_equity <= 0.5
              AND cfo_pat_ratio >= 0.80
              AND promoter_holding >= 50.0
              AND (pledge_pct = 0.0 OR pledge_pct IS NULL)
              AND (piotroski_score >= 6 OR (piotroski_score IS NULL AND f_score >= 6))
              AND market_cap_cr <= 5000
            ORDER BY ml_rank_score DESC, score DESC
        """
        records = await deps._run_blocking(deps._read_records, query)
        
        if not records:
            return []
            
        return deps._json_safe_clean(records)
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/thesis/{symbol}")
async def get_llm_thesis(symbol: str):
    """Generate concise AI investment thesis via local Ollama."""
    try:
        from modules.llm_engine import generate_thesis
        import pandas as pd
        conn = deps.get_connection()
        try:
            target = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
            if target.empty:
                return {"thesis": "Stock not found in database to generate thesis."}
            stock_data = target.iloc[0].to_dict()
        finally:
            conn.close()
            
        thesis = await deps._run_blocking(generate_thesis, stock_data)
        return {"thesis": thesis}
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/history/{symbol}")
def get_stock_history(symbol: str):
    """Fetch historical score data for a stock."""
    try:
        conn = deps.get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Normalize symbol
        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"
            
        cursor.execute("""
            SELECT as_of_date, score, price 
            FROM fundamentals_pit 
            WHERE symbol = ? 
            ORDER BY as_of_date ASC
        """, (symbol,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "date": row["as_of_date"],
                "score": row["score"],
                "price": row["price"]
            }
            for row in rows
        ]
    except Exception as e:
        deps.api_logger.warning("Failed to load stock history", symbol=symbol, error=str(e))
        return []

@router.get("/api/microcaps")
async def get_microcaps():
    """Fetch Hidden Microcap Gems"""
    try:
        return await deps._run_blocking(
            deps._read_records, "SELECT * FROM microcaps ORDER BY score DESC"
        )
    except Exception as e:
        return {"error": str(e)}

# Advanced Forensics API
@router.get("/api/liquidity")
def get_liquidity():
    try:
        if os.path.exists("liquidity.json"):
            with open("liquidity.json", "r") as f:
                return json.load(f)
        return {"error": "Report not generated yet."}
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/recovery")
def get_recovery():
    try:
        if os.path.exists("recovery.json"):
            with open("recovery.json", "r") as f:
                return json.load(f)
        return {"error": "Report not generated yet."}
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/thesis_break")
async def get_thesis_break():
    """Fetch all thesis break statuses (upgraded: live engine)."""
    try:
        from modules.thesis_monitor import check_all_thesis_breaks
        results = await deps._run_blocking(check_all_thesis_breaks)
        return {
            "timestamp": datetime.now().isoformat(),
            "signals_count": sum(1 for r in results if r["status"] == "THESIS_BREAK"),
            "status": "HEALTHY" if all(r["status"] in ("INTACT", "NO_THESIS", "NO_DATA") for r in results) else "ACTION_REQUIRED",
            "signals": results,
        }
    except Exception as e:
        # Fallback to legacy JSON
        if os.path.exists("thesis_break.json"):
            with open("thesis_break.json", "r") as f:
                return json.load(f)
        return {"error": str(e)}

@router.get("/api/thesis_status/{symbol}")
async def get_thesis_status(symbol: str):
    """Fetch thesis status for a single stock."""
    try:
        from modules.thesis_monitor import check_thesis, get_thesis_summary
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        status = await deps._run_blocking(check_thesis, symbol)
        thesis = await deps._run_blocking(get_thesis_summary, symbol)
        result = status.to_dict()
        if thesis:
            result["thesis_detail"] = thesis
        return result
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/rejections")
def get_rejections():
    """Fetch latest 20 rejected trades from Black Box Recorder"""
    try:
        if not os.path.exists("rejected_trades.csv"):
            return []
        with open("rejected_trades.csv", "r", encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            return rows[-20:][::-1]
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/regime_status", response_model=RegimeStatusResponse)
async def get_regime_status():
    """Fetch 3-Factor Regime Voting Status"""
    try:
        from modules.data_service import MarketDataProvider
        import config

        cache_key = f"{config.FORCED_REGIME or 'AUTO'}:{id(MarketDataProvider)}"
        if (
            deps._cache_is_fresh(deps.regime_cache, deps.REGIME_CACHE_TTL_SECONDS)
            and deps.regime_cache.get("key") == cache_key
        ):
            return deps.regime_cache["payload"]

        async with deps.regime_cache_lock:
            if (
                deps._cache_is_fresh(deps.regime_cache, deps.REGIME_CACHE_TTL_SECONDS)
                and deps.regime_cache.get("key") == cache_key
            ):
                return deps.regime_cache["payload"]
            provider = MarketDataProvider()
            data = await deps._run_blocking(provider.get_market_regime)

            # Check for Admin Override
            regime = data["regime"]
            if config.FORCED_REGIME:
                regime = config.FORCED_REGIME
                data["is_forced"] = True
            else:
                data["is_forced"] = False

            details = data.get("details", {})
            votes = data.get("votes", {})
           
            payload = {
                "regime": regime,
                "vix": details.get("vix", 0),
                "vix_threshold": 18.0,
                "momentum_accel": details.get("momentum_accel", 0),
                "votes": votes,
                "is_forced": data.get("is_forced", False),
                "details": details,
                "timestamp": datetime.now().strftime("%H:%M:%S"),
            }
            deps._cache_set(deps.regime_cache, payload)
            deps.regime_cache["key"] = cache_key
            return payload
    except Exception as e:
        cached_payload = deps.regime_cache.get("payload")
        if cached_payload:
            stale_payload = dict(cached_payload)
            stale_payload["stale"] = True
            stale_payload["error"] = str(e)
            return stale_payload
        raise HTTPException(status_code=500, detail=f"Failed to load regime status: {e}") from e


@router.post("/api/admin/force_regime")
def force_regime(regime: str):
    """Manually force the regime for next scans. options: BULL, BEAR, SIDEWAYS, AUTO"""
    try:
        import config
        
        regime = regime.upper()
        if regime not in ['BULL', 'BEAR', 'SIDEWAYS', 'AUTO']:
            raise HTTPException(status_code=400, detail="Invalid regime. Use BULL, BEAR, SIDEWAYS, or AUTO.")
            
        if regime == 'AUTO':
            config.FORCED_REGIME = None
            deps.runtime_logger.info("Regime override cleared; resuming auto mode")
        else:
            config.FORCED_REGIME = regime
            deps.runtime_logger.info("Regime forced by administrator", regime=regime)

        deps._cache_invalidate(deps.regime_cache)
        return {"status": "success", "regime": regime}

    except Exception as e:
        return {"error": str(e)}

@router.post("/api/order")
async def place_order(order: deps.OrderRequest):
    """Order lifecycle endpoint for paper execution (BUY/SELL)."""
    try:
        symbol = order.symbol.strip().upper()
        side = order.side.strip().upper()

        if not symbol:
            return {"status": "rejected", "error": "symbol is required"}

        if side not in {"BUY", "SELL"}:
            return {"status": "rejected", "error": "side must be BUY or SELL"}

        if "." not in symbol:
            symbol = f"{symbol}.NS"

        if side == "BUY":
            # Dynamic + static kill-switch checks.
            if order.current_vix is not None or order.drawdown_rate_weekly is not None:
                vix_for_check = order.current_vix if order.current_vix is not None else 0.0
                is_safe, message = deps.risk_governor.check_kill_switch(
                    vix_for_check,
                    drawdown_rate_weekly=order.drawdown_rate_weekly,
                )
                if not is_safe:
                    deps.risk_governor.log_rejected_trade(symbol, message, order.price)
                    return {
                        "status": "rejected",
                        "side": side,
                        "symbol": symbol,
                        "reason": message,
                    }

            # Pre-trade VaR budget gate.
            var_safe, var_message = deps.risk_governor.validate_var_budget(
                order.projected_var_pct,
                order.max_var_pct,
            )
            if not var_safe:
                return {
                    "status": "rejected",
                    "side": side,
                    "symbol": symbol,
                    "reason": var_message,
                }

            # Correlation stress gate.
            adjusted_qty = order.quantity
            if order.portfolio_correlation is not None:
                corr_factor = deps.risk_governor.validate_correlation_risk(
                    order.portfolio_correlation
                )
                if corr_factor <= 0:
                    return {
                        "status": "rejected",
                        "side": side,
                        "symbol": symbol,
                        "reason": "Correlation emergency de-risk triggered",
                    }
                adjusted_qty = max(1, int(round(order.quantity * corr_factor)))

            result = await deps._run_blocking(
                deps.portfolio_tracker.log_entry,
                symbol,
                order.price,
                order.score,
                adjusted_qty,
            )

            # Record buy thesis for thesis break detection
            if result.get("status") != "rejected":
                try:
                    from modules.thesis_monitor import record_buy_thesis
                    # Fetch current fundamental data for thesis snapshot
                    def _fetch_thesis_data():
                        conn_t = deps.get_connection()
                        try:
                            row = pd.read_sql(
                                "SELECT * FROM multibaggers WHERE symbol = ?",
                                conn_t, params=(symbol,)
                            )
                            return row.iloc[0].to_dict() if not row.empty else {}
                        finally:
                            conn_t.close()
                    stock_snapshot = await deps._run_blocking(_fetch_thesis_data)
                    if stock_snapshot:
                        await deps._run_blocking(
                            record_buy_thesis, symbol, stock_snapshot,
                            order.score, 0, "SIDEWAYS"
                        )
                except Exception as thesis_err:
                    deps.api_logger.warning(
                        "Thesis recording skipped",
                        symbol=symbol,
                        error=str(thesis_err),
                    )
        else:
            result = await deps._run_blocking(
                deps.portfolio_tracker.log_exit,
                symbol,
                order.price,
                order.reason,
            )

        if result.get("status") == "rejected":
            deps.risk_governor.log_rejected_trade(symbol, result.get("reason", "Order rejected"), order.price)

        return {
            "status": result.get("status", "accepted"),
            "side": side,
            "symbol": symbol,
            "quantity": adjusted_qty if side == "BUY" else order.quantity,
            "price": order.price,
            "reason": result.get("reason", order.reason),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/api/trades/open")
async def get_open_trades():
    try:
        df = await deps._run_blocking(deps.portfolio_tracker.get_open_positions)
        if df.empty:
            return []
        clean_df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
        return clean_df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/trades/history")
async def get_trade_history():
    try:
        df = await deps._run_blocking(deps.portfolio_tracker.get_trade_history)
        if df.empty:
            return []
        clean_df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
        return clean_df.to_dict(orient="records")
    except Exception as e:
        return {"error": str(e)}



@router.post("/api/scan")
async def run_scan():
    """Trigger a full market scan using screener.py"""
    try:
        import sys
        process = await asyncio.create_subprocess_exec(
            sys.executable, "screener.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        return {"status": "scan_initiated", "pid": process.pid}
    except Exception as e:
        return {"error": str(e)}

@router.get("/")
def read_root():
    return FileResponse("web-ui/index.html")

# Market Movers API (Phase 64)
@router.get("/api/market_movers")
async def get_market_movers():
    """Fetch Top Gainers, Losers, and Actively Traded.
    
    Note: This endpoint currently returns empty data.
    The original Alpha Vantage data source was removed.
    TODO: Implement via yfinance screener or NSE bhavcopy parsing.
    """
    try:
        if deps._cache_is_fresh(deps.movers_cache, deps.MOVERS_CACHE_TTL_SECONDS):
            return deps.movers_cache["payload"]

        async with deps.movers_cache_lock:
            if deps._cache_is_fresh(deps.movers_cache, deps.MOVERS_CACHE_TTL_SECONDS):
                return deps.movers_cache["payload"]
            payload = {
                "gainers": [],
                "losers": [],
                "active": [],
                "_status": "not_implemented",
                "_note": "Market movers data source pending. Connect to NSE bhavcopy or yfinance screener.",
            }
            deps._cache_set(deps.movers_cache, payload)
            return payload

    except Exception as e:
        cached_payload = deps.movers_cache.get("payload")
        if cached_payload:
            stale_payload = dict(cached_payload)
            stale_payload["stale"] = True
            stale_payload["error"] = str(e)
            return stale_payload
        return {"error": str(e)}



# Valuation API
@router.get("/api/valuation/{symbol}")
async def get_valuation(symbol: str, as_of_date: str | None = None):
    try:
        valuation_as_of = (as_of_date or datetime.now().date().isoformat())[:10]

        def _normalize_valuation_payload(payload: dict):
            if not payload:
                return payload

            def _component_or_none(value):
                try:
                    parsed = float(value)
                except (TypeError, ValueError):
                    return None
                if not np.isfinite(parsed) or parsed <= 0:
                    return None
                return parsed

            if isinstance(payload.get("components"), dict):
                components = payload.get("components", {})
                payload["components"] = {
                    "dcf": _component_or_none(components.get("dcf")),
                    "graham": _component_or_none(components.get("graham")),
                    "epv": _component_or_none(components.get("epv")),
                }
                payload.setdefault("symbol", symbol)
                payload.setdefault("as_of_date", valuation_as_of)
                if payload.get("intrinsic_value") in (0, 0.0):
                    payload["intrinsic_value"] = None
                return payload

            normalized = {
                "symbol": payload.get("symbol", symbol),
                "intrinsic_value": payload.get("intrinsic_value", 0) or None,
                "margin_of_safety": payload.get("margin_of_safety", 0),
                "verdict": payload.get("verdict", "UNKNOWN"),
                "confidence_score": payload.get("confidence_score"),
                "calculated_at": payload.get("calculated_at"),
                "as_of_date": payload.get("as_of_date") or valuation_as_of,
                "components": {
                    "dcf": _component_or_none(payload.get("dcf_value", 0)),
                    "graham": _component_or_none(payload.get("graham_value", 0)),
                    "epv": _component_or_none(payload.get("epv_value", 0)),
                },
            }
            return normalized

        def _ensure_valuation_table():
            conn = deps.get_connection()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS valuation_metrics (
                        symbol TEXT PRIMARY KEY,
                        dcf_value REAL,
                        graham_value REAL,
                        epv_value REAL,
                        intrinsic_value REAL,
                        margin_of_safety REAL,
                        verdict TEXT,
                        confidence_score INTEGER,
                        as_of_date TEXT,
                        calculated_at TIMESTAMP
                    )
                    """
                )
                columns = [row[1] for row in conn.execute("PRAGMA table_info(valuation_metrics)").fetchall()]
                if "as_of_date" not in columns:
                    conn.execute("ALTER TABLE valuation_metrics ADD COLUMN as_of_date TEXT")
                conn.commit()
            finally:
                conn.close()

        await deps._run_sqlite_write_with_retry(_ensure_valuation_table, "valuation table init")

        def _read_cached():
            conn = deps.get_connection()
            try:
                if as_of_date:
                    query = """
                        SELECT *
                        FROM valuation_metrics
                        WHERE symbol = ? AND as_of_date <= ?
                        ORDER BY as_of_date DESC, calculated_at DESC
                        LIMIT 1
                    """
                    existing_local = pd.read_sql(query, conn, params=(symbol, valuation_as_of))
                else:
                    query = """
                        SELECT *
                        FROM valuation_metrics
                        WHERE symbol = ?
                        ORDER BY calculated_at DESC
                        LIMIT 1
                    """
                    existing_local = pd.read_sql(query, conn, params=(symbol,))
                if not existing_local.empty:
                    return existing_local.iloc[0].to_dict()
                return None
            finally:
                conn.close()

        cached = await deps._run_blocking(_read_cached)
        if cached:
            return _normalize_valuation_payload(cached)

        ticker = yf.Ticker(symbol)

        info = await run_with_exponential_backoff(
            lambda: deps._run_blocking(lambda: ticker.info),
            context=f"yfinance valuation for {symbol}",
        )

        if not info:
            return {"error": f"Failed to fetch valuation data for {symbol} (Throttled)"}

        def _get(yahoo_key, default=0):
            val = info.get(yahoo_key)
            if val not in (None, 0, ""):
                return val
            return default

        data = {
            "current_price": _get("currentPrice", 0),
            "eps_ttm": _get("trailingEps", 0),
            "book_value_per_share": _get("bookValue", 0),
            "free_cash_flow_per_share": (
                (info.get("operatingCashflow", 0) - abs(info.get("capitalExpenditures", 0)))
                / info.get("sharesOutstanding", 1)
                if info.get("operatingCashflow")
                else 0
            ),
            "growth_rate_5y": _get("earningsGrowth", 0.10) * 100,
            "beta": _get("beta", 1.0),
            "data_source": "yahoo",
        }

        from modules.valuation import ValuationEngine

        engine = ValuationEngine(data)
        metrics = engine.get_intrinsic_value()

        def _write_valuation():
            conn = deps.get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO valuation_metrics
                    (symbol, dcf_value, graham_value, epv_value, intrinsic_value, margin_of_safety, verdict, confidence_score, as_of_date, calculated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol,
                        metrics["components"]["dcf"],
                        metrics["components"]["graham"],
                        metrics["components"]["epv"],
                        metrics["intrinsic_value"],
                        metrics["margin_of_safety"],
                        metrics["verdict"],
                        85,
                        valuation_as_of,
                        datetime.now(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

        await deps._run_sqlite_write_with_retry(_write_valuation, "valuation upsert")
        metrics["symbol"] = symbol
        metrics["as_of_date"] = valuation_as_of
        return deps._json_safe_clean(_normalize_valuation_payload(metrics))

    except Exception as e:
        deps.api_logger.error("Failed to load valuation metrics", symbol=symbol, error=str(e))
        return {"error": str(e)}



@router.get("/api/financials/{symbol}")
def get_financials(symbol: str):
    try:
        from modules.financials import get_quarterly_results
        return deps._json_safe_clean(get_quarterly_results(symbol))
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/governance/{symbol}")
async def get_governance_data(symbol: str):
    """Fetch 8-Point Governance Checklist Data"""
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
            
        def _fetch_gov_data():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            # Helper for safe extraction
            def get_val(key, default=None):
                v = info.get(key, default)
                return v if v is not None else default

            # Detect Sector for Debt/Equity logic
            sector = get_val('sector', 'Unknown')
            is_financial = 'Financial' in sector or 'Bank' in sector

            # 1. ROE
            roe_raw = get_val('returnOnEquity', 0)
            roe = round(roe_raw * 100, 2) if roe_raw else 0
            
            # 2. Debt/Equity
            de_raw = get_val('debtToEquity', 0)
            de = round(de_raw / 100, 2) if de_raw else 0
            
            # 3. Sales Growth (Quarterly YoY or TTM)
            sales_growth_raw = get_val('revenueGrowth', 0)
            sales_growth = round(sales_growth_raw * 100, 2) if sales_growth_raw else 0
            
            # 4. Profit Growth (Earnings Growth)
            profit_growth_raw = get_val('earningsGrowth', 0)
            profit_growth = round(profit_growth_raw * 100, 2) if profit_growth_raw else 0
            
            # 5. Promoter Holding
            promoter_holding_raw = get_val('heldPercentInsiders', 0)
            promoter_holding = round(promoter_holding_raw * 100, 2) if promoter_holding_raw else 0
            
            # 6. Pledged Algo (Not in YF usually, defaulting to 0 for check)
            pledged = 0 
            
            # 7. CFO/PAT Check (Need Cashflow and Net Income)
            cfo = get_val('operatingCashflow', 0)
            ni = get_val('netIncomeToCommon', 1) # Avoid div/0
            cfo_pat = round(cfo / ni, 2) if ni and cfo else 0
            
            return {
                "symbol": symbol,
                "sector": sector,
                "is_financial": is_financial,
                "roe": roe,
                "debt_to_equity": de,
                "sales_growth": sales_growth,
                "profit_growth": profit_growth,
                "promoter_holding": promoter_holding,
                "pledged_pct": pledged,
                "cfo_pat_ratio": cfo_pat
            }

        data = await deps._run_blocking(_fetch_gov_data)
        return data
        
    except Exception as e:
        return {"error": str(e)}

# Technicals API
@router.get("/api/peers/{symbol}")
async def get_stock_peers(symbol: str):
    """Fetch Sector Peers for Comparison"""
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"

        def _get_peers():
            conn = deps.get_connection()
            try:
                # 1. Get Target Metrics
                target_query = "SELECT symbol, sector, price as current_price, score as terminal_score, pe_ratio as pe, roe, debt_equity, rs_rating as price_change_3m FROM multibaggers WHERE symbol = ?"
                target = pd.read_sql(target_query, conn, params=(symbol,))
                if target.empty:
                    raise HTTPException(status_code=404, detail="Stock not found")
                
                start_sector = target.iloc[0]['sector']

                # 2. Get Peers using Subquery for Sector (More robust)
                query = """
                    SELECT symbol, symbol as name, price as current_price, score as terminal_score, pe_ratio as pe, roe, debt_equity, rs_rating as price_change_3m
                    FROM multibaggers 
                    WHERE sector = (SELECT sector FROM multibaggers WHERE symbol = ?) 
                    AND symbol != ?
                    ORDER BY score DESC
                    LIMIT 5
                """
                peers_df = pd.read_sql(query, conn, params=(symbol, symbol))
                peers = peers_df.to_dict(orient="records")
                
                # 3. Sector Averages
                avg_query = """
                    SELECT 
                        AVG(pe_ratio) as pe, 
                        AVG(roe) as roe, 
                        AVG(score) as terminal_score 
                    FROM multibaggers 
                    WHERE sector = (SELECT sector FROM multibaggers WHERE symbol = ?)
                """
                # Use execute directly for scalar values to avoid overhead? No, pandas is fine.
                avg_df = pd.read_sql(avg_query, conn, params=(symbol,))
                if not avg_df.empty:
                    avgs = avg_df.iloc[0].to_dict()
                else:
                    avgs = {}
                
                return {
                    "sector": start_sector,
                    "peers": peers,
                    "sector_avg": avgs,
                    "stock_metrics": target.iloc[0].to_dict(),
                    "rankings": {"score_rank_desc": "Top 10"}
                }
            finally:
                conn.close()

        return await deps._run_blocking(_get_peers)

    except Exception as e:
        return {"error": str(e)}

@router.get("/api/technicals/{symbol}")
async def get_technicals(symbol: str):
    try:
        from modules.technicals import get_technical_analysis
        return deps._json_safe_clean(await get_technical_analysis(symbol))
    except Exception as e:
        return {"error": str(e)}

# Shareholding API
# Promoter Intelligence API
@router.get("/api/promoter/{symbol}")
async def get_promoter_intel(symbol: str):
    """Fetch Promoter Behaviour Intelligence (trends, deals, pledge, scoring)."""
    try:
        from modules.promoter_intel import calculate_promoter_score
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        return await deps._run_blocking(calculate_promoter_score, symbol)
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/shareholding/{symbol}")
async def get_shareholding(symbol: str):
    try:
        from modules.shareholding import get_shareholding_pattern
        return deps._json_safe_clean(await get_shareholding_pattern(symbol))
    except Exception as e:
        return {"error": str(e)}

# Quarterly Results Timeline API
@router.get("/api/quarterly-results/{symbol}")
async def quarterly_results_endpoint(symbol: str, quarters: int = 12):
    import time
    start_time = time.time()
    try:
        # Check Cache
        if deps._cache_is_fresh(deps.CACHE_QUARTERLY.get(symbol, {}), deps.CACHE_AUDIT_TTL):
            deps.api_logger.info("Quarterly results cache hit", symbol=symbol)
            return deps.CACHE_QUARTERLY[symbol]["payload"]

        deps.api_logger.info("Quarterly results request started", symbol=symbol)
        from modules.quarterly_results import get_quarterly_timeline
        result = await get_quarterly_timeline(symbol, quarters)
        
        deps.api_logger.info(
            "Quarterly results fetched; cleaning payload",
            symbol=symbol,
            elapsed_seconds=round(time.time() - start_time, 2),
        )
        cleaned = deps._json_safe_clean(result)
        
        # Set Cache
        if symbol not in deps.CACHE_QUARTERLY: deps.CACHE_QUARTERLY[symbol] = {}
        deps._cache_set(deps.CACHE_QUARTERLY[symbol], cleaned)
        
        deps.api_logger.info(
            "Quarterly results cached",
            symbol=symbol,
            elapsed_seconds=round(time.time() - start_time, 2),
        )
        return cleaned
    except Exception as e:
        from fastapi import HTTPException
        deps.api_logger.error(
            "Quarterly results request failed",
            symbol=symbol,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch quarterly results: {str(e)}"
        )

# Price vs Fundamentals API
@router.get("/api/price-fundamentals/{symbol}")
async def price_fundamentals_endpoint(symbol: str, years: int = 5):
    import time
    start_time = time.time()
    try:
        years = min(max(years, 3), 10)
        cache_key = f"{symbol}:{years}"
        # Check Cache
        if deps._cache_is_fresh(deps.CACHE_FUNDAMENTALS.get(cache_key, {}), deps.CACHE_AUDIT_TTL):
            deps.api_logger.info(
                "Price fundamentals cache hit",
                symbol=symbol,
                years=years,
            )
            return deps.CACHE_FUNDAMENTALS[cache_key]["payload"]

        deps.api_logger.info(
            "Price fundamentals request started",
            symbol=symbol,
            years=years,
        )
        from modules.price_fundamentals import get_price_vs_fundamentals
        result = await get_price_vs_fundamentals(symbol, years)
        
        deps.api_logger.info(
            "Price fundamentals fetched; cleaning payload",
            symbol=symbol,
            years=years,
            elapsed_seconds=round(time.time() - start_time, 2),
        )
        cleaned = deps._json_safe_clean(result)
        
        # Set Cache
        if cache_key not in deps.CACHE_FUNDAMENTALS: deps.CACHE_FUNDAMENTALS[cache_key] = {}
        deps._cache_set(deps.CACHE_FUNDAMENTALS[cache_key], cleaned)
        
        deps.api_logger.info(
            "Price fundamentals cached",
            symbol=symbol,
            years=years,
            elapsed_seconds=round(time.time() - start_time, 2),
        )
        return cleaned
    except Exception as e:
        from fastapi import HTTPException
        deps.api_logger.error(
            "Price fundamentals request failed",
            symbol=symbol,
            years=years,
            error=str(e),
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch price vs fundamentals: {str(e)}"
        )

# Estimates Momentum API
@router.get("/api/estimates/{symbol}")
async def get_estimates(symbol: str):
    """Fetch forward-looking estimate momentum data."""
    try:
        from modules.estimates import get_estimate_data
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        return await deps._run_blocking(get_estimate_data, symbol)
    except Exception as e:
        return {"error": str(e)}

# AV Endpoints removed (API key dependency eliminated)

def weekly_audit_loop():
    """Compatibility wrapper around the standalone weekly audit worker."""
    run_weekly_audit_loop(
        deps.get_connection=deps.get_connection,
        run_sqlite_write_with_retry_sync=deps._run_sqlite_write_with_retry_sync,
        logger=deps.runtime_logger,
    )


@router.get("/api/swarm/{symbol}")
async def get_swarm_report(symbol: str):
    """Fetch Swarm Intelligence Validation Report from MiroFish."""
    try:
        from modules.mirofish_client import MiroFishClient
        from modules.symbol_utils import normalize_symbol
        import pandas as pd
        
        symbol = normalize_symbol(symbol)
        client = MiroFishClient()
        
        # 1. Fetch context from DB for the swarm debate
        def _fetch_context():
            conn = deps.get_connection()
            try:
                row = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
                if row.empty: return None
                data = row.iloc[0].to_dict()
                return f"Stock {symbol} in {data.get('sector')} sector. Score: {data.get('score')}. PE: {data.get('pe')}. ROE: {data.get('avg_roe_5y')}. Growth: {data.get('sales_cagr_5y')}."
            finally:
                conn.close()
        
        context = await deps._run_blocking(_fetch_context)
        if not context:
            raise HTTPException(status_code=404, detail="Stock not found in database.")
            
        # 2. Trigger/Retrieve Swarm Simulation
        report = await deps._run_blocking(client.simulate_ticker, symbol, context)
        
        return {
            "symbol": symbol,
            "report": report,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}



@router.get("/api/backtest-metrics")
async def get_backtest_metrics():
    """Fetch aggregate portfolio backtesting metrics."""
    import os
    try:
        if not os.path.exists("backtest_report.md"):
            return {"status": "pending"}
            
        metrics = {"status": "success"}
        with open("backtest_report.md", "r", encoding="utf-8") as f:
            for line in f:
                if "Average CAGR" in line:
                    metrics["cagr"] = line.split(":")[-1].replace("*", "").replace("%", "").strip()
                elif "Win Rate" in line:
                    metrics["win_rate"] = line.split(":")[-1].replace("*", "").replace("%", "").strip()
                elif "Max Drawdown" in line:
                    metrics["max_dd"] = line.split(":")[-1].replace("*", "").replace("%", "").strip()
                elif "Sharpe Ratio" in line:
                    metrics["sharpe"] = line.split(":")[-1].replace("*", "").strip()
                elif "Sortino Ratio" in line:
                    metrics["sortino"] = line.split(":")[-1].replace("*", "").strip()
                elif "Calmar Ratio" in line:
                    metrics["calmar"] = line.split(":")[-1].replace("*", "").strip()
                    
        return metrics
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/slippage_stats")
async def get_slippage_stats():
    """Fetch Execution Quality Metrics (Slippage Calibration)"""
    try:
        query = "SELECT * FROM slippage_metrics ORDER BY tier"
        data = await deps._run_blocking(deps._read_records, query)
        return deps._json_safe_clean(data)
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/revisions/{symbol}")
async def get_revisions(symbol: str):
    """Fetch analyst recommendations trend and score impact."""
    try:
        symbol = normalize_symbol(symbol)
        ticker = yf.Ticker(symbol)
        score_impact, sentiment = await deps._run_blocking(analyze_revisions, ticker)
        return {
            "symbol": symbol,
            "score_impact": score_impact,
            "sentiment": sentiment,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/drift/{symbol}")
async def get_drift(symbol: str):
    """Detect investment thesis drift for a single stock."""
    try:
        symbol = normalize_symbol(symbol)
        def _fetch_drift_data():
            conn = deps.get_connection()
            try:
                # Fetch recent technicals and fundamentals
                row = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
                if row.empty:
                    return None
                return row.iloc[0].to_dict()
            finally:
                conn.close()
        
        stock_data = await deps._run_blocking(_fetch_drift_data)
        if not stock_data:
            raise HTTPException(status_code=404, detail="Stock data not found")
            
        status, reason = monitor_drift(stock_data)
        return {
            "symbol": symbol,
            "status": status,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}

@router.get("/api/allocation/hrp")
@router.get("/api/hrp")
async def get_hrp_allocation():
    """Calculate HRP weights for top 15 stocks based on 1Y returns."""
    try:
        def _get_top_symbols():
            conn = deps.get_connection()
            try:
                df = pd.read_sql("SELECT symbol FROM multibaggers ORDER BY score DESC LIMIT 15", conn)
                return df["symbol"].tolist()
            finally:
                conn.close()
        
        symbols = await deps._run_blocking(_get_top_symbols)
        if not symbols:
            raise HTTPException(status_code=404, detail="No stocks found for allocation")
            
        # Download historical prices for 1 year
        data = await run_with_exponential_backoff(
            lambda: deps._run_ticker_blocking(
                yf.download,
                symbols,
                period="1y",
                interval="1d",
                progress=False,
                auto_adjust=True
            ),
            context="hrp allocation price fetch"
        )
        
        if data.empty:
            raise HTTPException(status_code=502, detail="Failed to fetch historical data")
            
        # Calculate returns - handle MultiIndex carefully
        if isinstance(data.columns, pd.MultiIndex):
            prices = data["Close"] if "Close" in data else data.xs('Close', axis=1, level=0)
        else:
            prices = data[["Close"]] if "Close" in data.columns else data
            
        returns = prices.pct_change().dropna(how='all').fillna(0)
        
        allocator = HRPAllocator()
        weights = allocator.allocate(returns)
        
        # Sort by weight descending
        sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        
        return {
            "weights": {k: float(v) for k, v in sorted_weights},
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"error": str(e)}


# Helper to clean JSON (NaN/Inf)
def deps._json_safe_clean(obj):
    if isinstance(obj, list):
        return [deps._json_safe_clean(x) for x in obj]
    if isinstance(obj, dict):
        return {k: deps._json_safe_clean(v) for k, v in obj.items()}
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
    return obj
