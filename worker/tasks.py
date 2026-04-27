# worker/tasks.py
"""
Sovereign AI Trading Engine v4.0 — Celery Task Definitions
Patched: all tasks decorated with celery_task_timer for Prometheus metrics.
"""
import os
import sys
import time
import traceback
import asyncio
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from worker.celery_app import app
from worker.redis_cache import cache

try:
    from monitoring.metrics import (
        celery_task_timer,
        record_scan_result,
        set_regime,
        timed_scan,
        LLM_THESIS_FALLBACK,
    )
except ImportError:
    # Graceful degradation if prometheus_client not installed
    def celery_task_timer(name):
        def decorator(fn): return fn
        return decorator
    def record_scan_result(*a, **kw): pass
    def set_regime(*a): pass
    def timed_scan():
        from contextlib import contextmanager
        @contextmanager
        def _noop(): yield
        return _noop()
    class _Noop:
        def inc(self): pass
    LLM_THESIS_FALLBACK = _Noop()


# ════════════════════════════════════════════════════════════════════════════
# SCREENING TASKS
# ════════════════════════════════════════════════════════════════════════════

@app.task(bind=True, name="worker.tasks.scan_single_stock", max_retries=3, rate_limit="20/m")
@celery_task_timer("scan_single_stock")
def scan_single_stock(self, symbol: str, regime: str = "SIDEWAYS"):
    """
    Scan a single stock through the full scoring pipeline.
    Atomic unit of work for distributed screening.
    """
    try:
        cached = cache.get_stock_score(symbol)
        if cached:
            record_scan_result("cached")
            return {"symbol": symbol, "cached": True, **cached}

        # Use sync wrapper to avoid asyncio.run() loop-per-task anti-pattern
        from modules.data_service import data_manager
        from scripts.internal.screener import get_stock_data_sync
        from modules.scoring import calculate_institutional_score
        
        stock_data = get_stock_data_sync(symbol, dm=data_manager, include_quarterly=False)

        if not stock_data or stock_data.get("_fetch_error"):
            record_scan_result("skipped")
            return {
                "symbol": symbol,
                "error": stock_data.get("_fetch_error", "No data available") if stock_data else "No data available",
                "score": 0,
            }

        score_payload = calculate_institutional_score(stock_data, market_regime=regime)
        score = float(score_payload.get("total_score", 0.0) or 0.0)
        stock_data["Score"] = score
        stock_data["Data_Confidence"] = score_payload.get("data_confidence", 0.0)

        result = {
            **stock_data,
            "symbol": stock_data.get("Symbol", symbol),
            "score": score,
            "price": stock_data.get("Price"),
            "sector": stock_data.get("Sector"),
            "pe_ratio": stock_data.get("PE_Ratio"),
            "roe": stock_data.get("ROE%"),
            "data_quality": stock_data.get("Data_Quality", stock_data.get("Data_Confidence", 0)),
            "scanned_at": datetime.now().isoformat(),
            "regime": regime,
        }

        cache.cache_stock_score(symbol, result)
        record_scan_result(
            "success",
            score=result["score"],
            dq=result.get("data_quality"),
        )
        return result

    except Exception as exc:
        record_scan_result("error")
        print(f"Task scan_single_stock failed for {symbol}: {exc}")
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1))


@app.task(bind=True, name="worker.tasks.run_full_scan", time_limit=3600)
@celery_task_timer("run_full_scan")
def run_full_scan(self):
    """
    Orchestrate a full-universe scan by fanning out individual stock scans.
    Records total scan duration via Prometheus.
    """
    from celery import group

    try:
        from ticker_list import STOCK_LIST
        symbols = STOCK_LIST if isinstance(STOCK_LIST, list) else list(STOCK_LIST)

        regime = "SIDEWAYS"
        cached_regime = cache.get_regime()
        if cached_regime:
            regime = cached_regime.get("regime", "SIDEWAYS")

        set_regime(regime)
        print(f"Full scan: {len(symbols)} symbols | Regime: {regime}")

        with timed_scan():
            job = group(scan_single_stock.s(symbol, regime) for symbol in symbols)
            result = job.apply_async()
            results = result.get(timeout=2400, propagate=False)

        successful = [r for r in results if isinstance(r, dict) and "error" not in r]
        failed = len(results) - len(successful)
        print(f"Scan complete: {len(successful)} success / {failed} failed")

        if successful:
            import pandas as pd
            from db.repository import save_multibaggers
            df = pd.DataFrame(successful)
            save_multibaggers(df)

        return {
            "total": len(symbols),
            "success": len(successful),
            "failed": failed,
            "regime": regime,
            "completed_at": datetime.now().isoformat(),
        }

    except Exception as exc:
        print(f"Full scan failed: {exc}")
        traceback.print_exc()
        return {"error": str(exc)}


# ════════════════════════════════════════════════════════════════════════════
# ML INFERENCE TASKS
# ════════════════════════════════════════════════════════════════════════════

@app.task(name="worker.tasks.retrain_xgboost", time_limit=1800)
@celery_task_timer("retrain_xgboost")
def retrain_xgboost():
    try:
        from modules.hybrid_scoring import train_hybrid_model
        result = train_hybrid_model()
        return {"status": "success", "retrained_at": datetime.now().isoformat(), "result": str(result)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.generate_thesis", rate_limit="5/m")
@celery_task_timer("generate_thesis")
def generate_thesis(stock_data: dict):
    try:
        from modules.llm_engine import generate_thesis as _gen, generate_rule_based_thesis
        # Detect whether the response is the rule-based fallback
        thesis = _gen(stock_data)
        if "Rule-Based Engine" in thesis:
            LLM_THESIS_FALLBACK.inc()
        return {
            "symbol": stock_data.get("symbol", "UNKNOWN"),
            "thesis": thesis,
            "generated_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"symbol": stock_data.get("symbol", "UNKNOWN"), "error": str(e)}


# ════════════════════════════════════════════════════════════════════════════
# BACKTEST TASKS
# ════════════════════════════════════════════════════════════════════════════

@app.task(name="worker.tasks.run_backtest_refresh", time_limit=3600)
@celery_task_timer("run_backtest_refresh")
def run_backtest_refresh():
    try:
        from scripts.internal.backtest_engine import run_backtest
        result = run_backtest()
        return {"status": "success", "refreshed_at": datetime.now().isoformat(), "result": str(result)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ════════════════════════════════════════════════════════════════════════════
# MAINTENANCE TASKS
# ════════════════════════════════════════════════════════════════════════════

@app.task(name="worker.tasks.prune_pit_data")
@celery_task_timer("prune_pit_data")
def prune_pit_data():
    try:
        from db.repository import prune_fundamentals_pit_retention
        deleted = prune_fundamentals_pit_retention()
        return {"status": "success", "rows_pruned": deleted, "pruned_at": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.refresh_regime_cache")
@celery_task_timer("refresh_regime_cache")
def refresh_regime_cache():
    try:
        from modules.data_service import MarketDataProvider
        regime_data = MarketDataProvider().get_market_regime()
        cache.cache_regime(regime_data)
        set_regime(regime_data.get("regime", "SIDEWAYS"))
        return {"status": "success", "regime": regime_data.get("regime"), "cached_at": datetime.now().isoformat()}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.run_paper_trade")
@celery_task_timer("run_paper_trade")
def run_paper_trade():
    try:
        from sovereign_cli import cmd_paper_trade
        # Create a dummy args object for the command
        class Args:
            pass
        args = Args()
        args.regime = None # Auto-detect
        
        from modules.data_utils import run_coroutine_sync
        result = run_coroutine_sync(cmd_paper_trade(args))
        return {
            "status": "success",
            "executed_at": datetime.now().isoformat(),
            "signal": result
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.run_stress_test")
@celery_task_timer("run_stress_test")
def run_stress_test(portfolio: dict):
    try:
        from modules.stress_tester import run_all_scenarios
        reports = run_all_scenarios(portfolio)
        return {
            "status": "success",
            "scenario_count": len(reports),
            "worst_case_loss_pct": reports[0].portfolio_loss_pct if reports else None,
            "tested_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
