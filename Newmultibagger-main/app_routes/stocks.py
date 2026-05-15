from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException

import modules.dependencies as deps
from modules.retry_utils import run_with_exponential_backoff

router = APIRouter()


@router.get("/api/stocks")
async def get_multibaggers(as_of_date: str | None = None):
    """Fetch Top Multibagger Picks using DuckDB for rapid sorting and filtering"""
    try:
        from db.db_core import duck_conn

        if as_of_date:
            from db.repository import load_fundamentals_universe_as_of

            def _read_as_of_records():
                df, snapshot_date = load_fundamentals_universe_as_of(as_of_date)
                if df.empty:
                    return []
                df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
                records = df.to_dict(orient="records")
                for record in records:
                    if not record.get("as_of_date"):
                        record["as_of_date"] = snapshot_date
                return records

            return await deps._run_blocking(_read_as_of_records)

        # Vectorized DuckDB Sorting
        def _run_duckdb_sort():
            df = duck_conn.execute(
                "SELECT * FROM sqlite_db.multibaggers ORDER BY CAST(score AS DOUBLE) DESC, CAST(rs_rating AS DOUBLE) DESC, CAST(market_cap_cr AS DOUBLE) DESC"
            ).df()
            if df.empty:
                return []
            import json

            df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
            return json.loads(df.to_json(orient="records", double_precision=2))

        records = await deps._run_blocking(_run_duckdb_sort)

        if not records:
            return []

        return deps._json_safe_clean(records)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch stocks: {e}")


@router.get("/api/multibagger-hunt")
async def get_multibagger_hunt():
    """Fetch stocks meeting the strict Multibagger Hunt criteria using DuckDB for speed"""
    try:
        query = """
            SELECT * FROM sqlite_db.multibaggers
            WHERE CAST(sales_cagr_5y AS DOUBLE) >= 0.15
              AND CAST(avg_roe_5y AS DOUBLE) >= 0.15
              AND CAST(debt_equity AS DOUBLE) <= 0.5
              AND CAST(cfo_pat_ratio AS DOUBLE) >= 0.80
              AND CAST(promoter_holding AS DOUBLE) >= 50.0
              AND (CAST(pledge_pct AS DOUBLE) = 0.0 OR pledge_pct IS NULL)
              AND (CAST(piotroski_score AS DOUBLE) >= 6 OR (piotroski_score IS NULL AND CAST(f_score AS DOUBLE) >= 6))
              AND CAST(market_cap_cr AS DOUBLE) <= 5000
            ORDER BY CAST(ml_rank_score AS DOUBLE) DESC, CAST(score AS DOUBLE) DESC
        """

        def _run_duckdb_query():
            from db.db_core import duck_conn

            # Execute natively in DuckDB and fetch as Pandas DataFrame
            df = duck_conn.execute(query).df()
            if df.empty:
                return []
            import json

            import numpy as np

            df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
            return json.loads(df.to_json(orient="records", double_precision=2))

        records = await deps._run_blocking(_run_duckdb_query)

        if not records:
            return []

        return deps._json_safe_clean(records)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch multibagger hunt: {e}")


@router.get("/api/thesis/{symbol}")
async def get_llm_thesis(symbol: str):
    """Generate concise AI investment thesis via local Ollama."""
    try:
        from sqlalchemy import text

        from modules.llm_engine import generate_thesis

        with deps.get_sqla_connection() as conn:
            target = pd.read_sql(
                text("SELECT * FROM multibaggers WHERE symbol = :symbol"),
                conn,
                params={"symbol": symbol},
            )
            if target.empty:
                return {"thesis": "Stock not found in database to generate thesis."}
            stock_data = target.iloc[0].to_dict()

        thesis = await deps._run_blocking(generate_thesis, stock_data)
        return {"thesis": thesis}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Thesis generation failed: {e}")


@router.get("/api/history/{symbol}")
async def get_stock_history(symbol: str):
    """Fetch historical score data for a stock using DuckDB."""
    try:
        from db.db_core import duck_conn

        if not symbol.endswith(".NS"):
            symbol = f"{symbol}.NS"

        def _fetch_history():
            # DuckDB is highly optimized for point-in-time aggregations
            return duck_conn.execute(
                """
                SELECT as_of_date as date, CAST(score AS DOUBLE) as score, CAST(price AS DOUBLE) as price
                FROM sqlite_db.fundamentals_pit
                WHERE symbol = ?
                ORDER BY as_of_date ASC
            """,
                (symbol,),
            ).df()

        df = await deps._run_blocking(_fetch_history)
        if df.empty:
            return []

        import json

        df = df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
        return json.loads(df.to_json(orient="records", double_precision=2))

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
        raise HTTPException(status_code=500, detail=f"Failed to fetch microcaps: {e}")


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
        raise HTTPException(status_code=500, detail=f"Thesis status check failed: {e}")


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
                except:
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

            return {
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

        def _ensure_valuation_table():
            from sqlalchemy import text

            with deps.get_sqla_connection() as conn:
                conn.execute(
                    text(
                        "CREATE TABLE IF NOT EXISTS valuation_metrics (symbol TEXT PRIMARY KEY, dcf_value REAL, graham_value REAL, epv_value REAL, intrinsic_value REAL, margin_of_safety REAL, verdict TEXT, confidence_score INTEGER, as_of_date TEXT, calculated_at TIMESTAMP)"
                    )
                )

                # SQLAlchemy agnostic column check
                if deps.db_engine.dialect.name == "sqlite":
                    columns = [
                        row[1]
                        for row in conn.execute(
                            text("PRAGMA table_info(valuation_metrics)")
                        ).fetchall()
                    ]
                else:
                    columns = [
                        row[0]
                        for row in conn.execute(
                            text(
                                "SELECT column_name FROM information_schema.columns WHERE table_name='valuation_metrics'"
                            )
                        ).fetchall()
                    ]

                if "as_of_date" not in columns:
                    conn.execute(text("ALTER TABLE valuation_metrics ADD COLUMN as_of_date TEXT"))
                conn.commit()

        await deps._run_sqlite_write_with_retry(_ensure_valuation_table, "valuation table init")

        def _read_cached():
            from sqlalchemy import text

            with deps.get_sqla_connection() as conn:
                if as_of_date:
                    query = "SELECT * FROM valuation_metrics WHERE symbol = :symbol AND as_of_date <= :as_of_date ORDER BY as_of_date DESC, calculated_at DESC LIMIT 1"
                    existing_local = pd.read_sql(
                        text(query), conn, params={"symbol": symbol, "as_of_date": valuation_as_of}
                    )
                else:
                    query = "SELECT * FROM valuation_metrics WHERE symbol = :symbol ORDER BY calculated_at DESC LIMIT 1"
                    existing_local = pd.read_sql(text(query), conn, params={"symbol": symbol})
                return existing_local.iloc[0].to_dict() if not existing_local.empty else None

        cached = await deps._run_blocking(_read_cached)
        if cached:
            return _normalize_valuation_payload(cached)

        ticker = yf.Ticker(symbol)
        info = await run_with_exponential_backoff(
            lambda: deps._run_blocking(lambda: ticker.info), context=f"yf valuation {symbol}"
        )
        if not info:
            return {"error": f"Failed to fetch valuation for {symbol}"}

        from modules.valuation import ValuationEngine

        data = {
            "current_price": info.get("currentPrice", 0),
            "eps_ttm": info.get("trailingEps", 0),
            "book_value_per_share": info.get("bookValue", 0),
            "free_cash_flow_per_share": (
                (info.get("operatingCashflow", 0) - abs(info.get("capitalExpenditures", 0)))
                / info.get("sharesOutstanding", 1)
            )
            if info.get("operatingCashflow")
            else 0,
            "growth_rate_5y": info.get("earningsGrowth", 0.10) * 100,
            "beta": info.get("beta", 1.0),
            "data_source": "yahoo",
        }
        engine = ValuationEngine(data)
        metrics = engine.get_intrinsic_value()

        def _write_valuation():
            from sqlalchemy import text

            # Phase 3.4: Derive confidence from actual input completeness
            confidence = 40  # Base confidence for having some data
            if data.get("eps_ttm") and data["eps_ttm"] > 0:
                confidence += 15
            if data.get("book_value_per_share") and data["book_value_per_share"] > 0:
                confidence += 15
            if data.get("free_cash_flow_per_share") and data["free_cash_flow_per_share"] > 0:
                confidence += 15
            if data.get("growth_rate_5y") and data["growth_rate_5y"] > 0:
                confidence += 15

            with deps.get_sqla_connection() as conn:
                # Use standard insert since 'INSERT OR REPLACE' is SQLite specific
                # For PostgreSQL compatibility we'd use ON CONFLICT but for now delete and insert works generically
                conn.execute(
                    text("DELETE FROM valuation_metrics WHERE symbol = :symbol"), {"symbol": symbol}
                )
                conn.execute(
                    text(
                        "INSERT INTO valuation_metrics (symbol, dcf_value, graham_value, epv_value, intrinsic_value, margin_of_safety, verdict, confidence_score, as_of_date, calculated_at) VALUES (:symbol, :dcf, :graham, :epv, :intrinsic, :margin, :verdict, :confidence, :as_of, :calc)"
                    ),
                    {
                        "symbol": symbol,
                        "dcf": metrics["components"]["dcf"],
                        "graham": metrics["components"]["graham"],
                        "epv": metrics["components"]["epv"],
                        "intrinsic": metrics["intrinsic_value"],
                        "margin": metrics["margin_of_safety"],
                        "verdict": metrics["verdict"],
                        "confidence": confidence,
                        "as_of": valuation_as_of,
                        "calc": datetime.now(),
                    },
                )
                conn.commit()

        await deps._run_sqlite_write_with_retry(_write_valuation, "valuation upsert")
        metrics["symbol"] = symbol
        metrics["as_of_date"] = valuation_as_of
        return deps._json_safe_clean(_normalize_valuation_payload(metrics))
    except Exception as e:
        deps.api_logger.error("Valuation failed", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=f"Valuation failed: {e}")


@router.get("/api/financials/{symbol}")
async def get_financials(symbol: str):
    try:
        from modules.financials import get_quarterly_results

        return deps._json_safe_clean(get_quarterly_results(symbol))
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/governance/{symbol}")
async def get_governance_data(symbol: str):
    """8-Point Governance Checklist Data"""
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"

        def _fetch_gov_data():
            ticker = yf.Ticker(symbol)
            info = ticker.info

            def get_val(key, default=None):
                val = info.get(key)
                return val if val is not None else default

            sector = get_val("sector", "Unknown")
            roe_raw = get_val("returnOnEquity", 0)
            roe = round(roe_raw * 100, 2) if roe_raw is not None else 0
            de_raw = get_val("debtToEquity", 0)
            de = round(de_raw / 100, 2) if de_raw and de_raw != 0 else 0
            sales_growth = round(get_val("revenueGrowth", 0) * 100, 2)
            profit_growth = round(get_val("earningsGrowth", 0) * 100, 2)
            promoter = round(get_val("heldPercentInsiders", 0) * 100, 2)
            cfo = get_val("operatingCashflow", 0)
            ni = get_val("netIncomeToCommon", 0)
            return {
                "symbol": symbol,
                "sector": sector,
                "is_financial": "Financial" in sector or "Bank" in sector,
                "roe": roe,
                "debt_to_equity": de,
                "sales_growth": sales_growth,
                "profit_growth": profit_growth,
                "promoter_holding": promoter,
                "pledged_pct": 0,
                "cfo_pat_ratio": round(cfo / ni, 2) if ni and ni != 0 else 0,
            }

        return await deps._run_blocking(_fetch_gov_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Governance data fetch failed: {e}")


@router.get("/api/peers/{symbol}")
async def get_stock_peers(symbol: str):
    """Sector Peers Comparison via DuckDB Aggregations"""
    try:
        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"

        def _get_peers():
            import json

            from db.db_core import duck_conn

            # Fetch target stock
            target_df = duck_conn.execute(
                "SELECT symbol, sector, CAST(price AS DOUBLE) as current_price, CAST(score AS DOUBLE) as terminal_score, CAST(pe_ratio AS DOUBLE) as pe, CAST(roe AS DOUBLE) as roe, CAST(debt_equity AS DOUBLE) as debt_equity, CAST(rs_rating AS DOUBLE) as price_change_3m FROM sqlite_db.multibaggers WHERE symbol = ?",
                (symbol,),
            ).df()
            if target_df.empty:
                raise HTTPException(status_code=404, detail="Stock not found")
            sector = target_df.iloc[0]["sector"]

            # Vectorized peer selection
            peers_df = duck_conn.execute(
                "SELECT symbol, symbol as name, CAST(price AS DOUBLE) as current_price, CAST(score AS DOUBLE) as terminal_score, CAST(pe_ratio AS DOUBLE) as pe, CAST(roe AS DOUBLE) as roe, CAST(debt_equity AS DOUBLE) as debt_equity, CAST(rs_rating AS DOUBLE) as price_change_3m FROM sqlite_db.multibaggers WHERE sector = ? AND symbol != ? ORDER BY CAST(score AS DOUBLE) DESC LIMIT 5",
                (sector, symbol),
            ).df()

            # Lightning fast sector aggregation
            avgs_df = duck_conn.execute(
                "SELECT AVG(CAST(pe_ratio AS DOUBLE)) as pe, AVG(CAST(roe AS DOUBLE)) as roe, AVG(CAST(score AS DOUBLE)) as terminal_score FROM sqlite_db.multibaggers WHERE sector = ?",
                (sector,),
            ).df()

            # Cleanup for JSON
            target_df = target_df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
            peers_df = peers_df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})
            avgs_df = avgs_df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None})

            return {
                "sector": sector,
                "peers": json.loads(peers_df.to_json(orient="records")),
                "sector_avg": avgs_df.iloc[0].to_dict(),
                "stock_metrics": target_df.iloc[0].to_dict(),
                "rankings": {"score_rank_desc": "Top 10"},
            }

        return await deps._run_blocking(_get_peers)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Peer comparison failed: {e}")


@router.get("/api/technicals/{symbol}")
async def get_technicals(symbol: str):
    try:
        from modules.technicals import get_technical_analysis

        return deps._json_safe_clean(await get_technical_analysis(symbol))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Technical analysis failed: {e}")


@router.get("/api/promoter/{symbol}")
async def get_promoter_intel(symbol: str):
    try:
        from modules.promoter_intel import calculate_promoter_score

        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        return await deps._run_blocking(calculate_promoter_score, symbol)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Promoter intel failed: {e}")


@router.get("/api/shareholding/{symbol}")
async def get_shareholding(symbol: str):
    try:
        from modules.shareholding import get_shareholding_pattern

        return deps._json_safe_clean(await get_shareholding_pattern(symbol))
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/quarterly-results/{symbol}")
async def quarterly_results_endpoint(symbol: str, quarters: int = 12):
    try:
        from modules.quarterly_results import get_quarterly_timeline

        if deps._cache_is_fresh(deps.CACHE_QUARTERLY.get(symbol, {}), deps.CACHE_AUDIT_TTL):
            return deps.CACHE_QUARTERLY[symbol]["payload"]
        result = await get_quarterly_timeline(symbol, quarters)
        cleaned = deps._json_safe_clean(result)
        if symbol not in deps.CACHE_QUARTERLY:
            deps.CACHE_QUARTERLY[symbol] = {}
        deps._cache_set(deps.CACHE_QUARTERLY[symbol], cleaned)
        return cleaned
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch quarterly results: {e}")


@router.get("/api/price-fundamentals/{symbol}")
async def price_fundamentals_endpoint(symbol: str, years: int = 5):
    try:
        years = min(max(years, 3), 10)
        cache_key = f"{symbol}:{years}"
        if deps._cache_is_fresh(deps.CACHE_FUNDAMENTALS.get(cache_key, {}), deps.CACHE_AUDIT_TTL):
            return deps.CACHE_FUNDAMENTALS[cache_key]["payload"]
        from modules.price_fundamentals import get_price_vs_fundamentals

        result = await get_price_vs_fundamentals(symbol, years)
        cleaned = deps._json_safe_clean(result)
        if cache_key not in deps.CACHE_FUNDAMENTALS:
            deps.CACHE_FUNDAMENTALS[cache_key] = {}
        deps._cache_set(deps.CACHE_FUNDAMENTALS[cache_key], cleaned)
        return cleaned
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch price vs fundamentals: {e}")


@router.get("/api/estimates/{symbol}")
async def get_estimates(symbol: str):
    try:
        from modules.estimates import get_estimate_data

        if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
            symbol += ".NS"
        return await deps._run_blocking(get_estimate_data, symbol)
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/swarm/{symbol}")
async def get_swarm_report_simulation(symbol: str):
    """Trigger Swarm Intelligence simulation via MiroFish."""
    try:
        from modules.mirofish_client import MiroFishClient

        client = MiroFishClient()

        def _fetch_context():
            from sqlalchemy import text

            with deps.get_sqla_connection() as conn:
                row = pd.read_sql(
                    text(
                        "SELECT symbol, sector, score, pe_ratio as pe, roe, sales_cagr_5y FROM multibaggers WHERE symbol = :symbol"
                    ),
                    conn,
                    params={"symbol": symbol},
                )
                if row.empty:
                    return None
                d = row.iloc[0].to_dict()
                return f"Stock {symbol} in {d['sector']}. Score: {d['score']}. PE: {d['pe']}. ROE: {d['roe']}. Growth: {d['sales_cagr_5y']}."

        context = await deps._run_blocking(_fetch_context)
        if not context:
            raise HTTPException(status_code=404, detail="Stock not found")
        report = await deps._run_blocking(client.simulate_ticker, symbol, context)
        return {"symbol": symbol, "report": report, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"error": str(e)}
