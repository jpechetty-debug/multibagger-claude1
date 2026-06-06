# worker/tasks.py
"""
Sovereign AI Trading Engine v4.0 — Celery Task Definitions
Patched: all tasks decorated with celery_task_timer for Prometheus metrics.
All logging via SovereignLogger (structured JSON + console).
"""

import os
import sys
import traceback
from datetime import datetime
from typing import Any

from core.observability.logger import get_logger

logger = get_logger("sovereign.worker.tasks")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from worker.celery_app import app
from worker.redis_cache import cache

try:
    from monitoring.metrics import (
        LLM_THESIS_FALLBACK,
        celery_task_timer,
        record_scan_result,
        set_regime,
        timed_scan,
    )
except ImportError:
    # Graceful degradation if prometheus_client not installed
    from collections.abc import Callable

    def celery_task_timer(task_name: str) -> Callable:
        def decorator(fn):
            return fn

        return decorator

    def record_scan_result(outcome: str, score: float | None = None, dq: float | None = None):
        pass

    def set_regime(regime: str):
        pass

    def timed_scan():
        from contextlib import contextmanager

        @contextmanager
        def _noop():
            yield

        return _noop()

    class _Noop:
        def inc(self):
            pass

    LLM_THESIS_FALLBACK: Any = _Noop()  # type: ignore[no-redef]


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
        from modules.data_service import get_data_manager
        from modules.scoring import calculate_institutional_score
        from scripts.internal.screener import get_stock_data_sync

        stock_data = get_stock_data_sync(symbol, dm=get_data_manager(), include_quarterly=False)

        if not stock_data or stock_data.get("_fetch_error"):
            record_scan_result("skipped")
            return {
                "symbol": symbol,
                "error": stock_data.get("_fetch_error", "No data available")
                if stock_data
                else "No data available",
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
        logger.error("scan_single_stock.failed", symbol=symbol, error=str(exc))
        raise self.retry(exc=exc, countdown=30 * (self.request.retries + 1)) from exc


@app.task(bind=True, name="worker.tasks.run_full_scan", time_limit=3600)
@celery_task_timer("run_full_scan")
def run_full_scan(self):
    """
    Orchestrate a full-universe scan by fanning out individual stock scans.
    Records total scan duration via Prometheus.
    """
    from celery import group

    try:
        from ticker_list import STOCK_LIST  # type: ignore

        symbols = STOCK_LIST if isinstance(STOCK_LIST, list) else list(STOCK_LIST)

        regime = "SIDEWAYS"
        cached_regime = cache.get_regime()
        if cached_regime:
            regime = cached_regime.get("regime", "SIDEWAYS")

        set_regime(regime)
        logger.info("full_scan.started", symbol_count=len(symbols), regime=regime)

        with timed_scan():
            job = group(scan_single_stock.s(symbol, regime) for symbol in symbols)
            result = job.apply_async()
            results = result.get(timeout=2400, propagate=False)

        successful = [r for r in results if isinstance(r, dict) and "error" not in r]
        failed = len(results) - len(successful)
        logger.info("full_scan.completed", success=len(successful), failed=failed)

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
        logger.error("full_scan.failed", error=str(exc))
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
        return {
            "status": "success",
            "retrained_at": datetime.now().isoformat(),
            "result": str(result),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.generate_thesis", rate_limit="5/m")
@celery_task_timer("generate_thesis")
def generate_thesis(stock_data: dict):
    try:
        from modules.llm_engine import generate_thesis as _gen

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
        return {
            "status": "success",
            "refreshed_at": datetime.now().isoformat(),
            "result": str(result),
        }
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
        return {
            "status": "success",
            "rows_pruned": deleted,
            "pruned_at": datetime.now().isoformat(),
        }
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
        return {
            "status": "success",
            "regime": regime_data.get("regime"),
            "cached_at": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.task(name="worker.tasks.run_paper_trade")
@celery_task_timer("run_paper_trade")
def run_paper_trade():
    try:
        from sovereign_cli import cmd_paper_trade

        # Create a dummy args object for the command
        class Args:
            regime: Any = None

        args = Args()

        from modules.data_utils import run_coroutine_sync

        result = run_coroutine_sync(cmd_paper_trade(args))
        return {"status": "success", "executed_at": datetime.now().isoformat(), "signal": result}
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
 
 @ a p p . t a s k ( b i n d = T r u e ,   n a m e = " w o r k e r . t a s k s . r e f r e s h _ s t a l e _ d a t a " ,   m a x _ r e t r i e s = 3 ,   r a t e _ l i m i t = " 1 0 / m " )  
 @ c e l e r y _ t a s k _ t i m e r ( " r e f r e s h _ s t a l e _ d a t a " )  
 d e f   r e f r e s h _ s t a l e _ d a t a ( s e l f ,   s y m b o l :   s t r ) :  
         " " "  
         B a c k g r o u n d   r e f r e s h   t r i g g e r e d   b y   s t a l e   d a t a   d e t e c t i o n .  
         B y p a s s e s   c a c h e   a n d   f o r c e f u l l y   f e t c h e s   f r e s h   f u n d a m e n t a l s .  
         " " "  
         t r y :  
                 f r o m   m o d u l e s . d a t a _ s e r v i c e   i m p o r t   g e t _ d a t a _ m a n a g e r  
                 f r o m   m o d u l e s . d a t a _ u t i l s   i m p o r t   r u n _ c o r o u t i n e _ s y n c  
                 f r o m   m o d u l e s . d b _ u t i l s   i m p o r t   g e t _ d b _ c o n n e c t i o n  
                  
                 d m   =   g e t _ d a t a _ m a n a g e r ( )  
                 c a c h e _ k e y   =   f " f u n d _ { s y m b o l } "  
                  
                 t r y :  
                         w i t h   g e t _ d b _ c o n n e c t i o n ( d m . c a c h e . d b _ n a m e )   a s   c o n n :  
                                 c o n n . e x e c u t e ( " D E L E T E   F R O M   c a c h e   W H E R E   k e y   =   ? " ,   ( c a c h e _ k e y , ) )  
                                 c o n n . c o m m i t ( )  
                 e x c e p t   E x c e p t i o n :  
                         p a s s  
                          
                 r u n _ c o r o u t i n e _ s y n c ( d m . a s y n c _ f e t c h _ f u n d a m e n t a l s ( s y m b o l ) )  
                 r e t u r n   { " s y m b o l " :   s y m b o l ,   " s t a t u s " :   " r e f r e s h e d " }  
         e x c e p t   E x c e p t i o n   a s   e x c :  
                 l o g g e r . e r r o r ( " r e f r e s h _ s t a l e _ d a t a . f a i l e d " ,   s y m b o l = s y m b o l ,   e r r o r = s t r ( e x c ) )  
                 r a i s e   s e l f . r e t r y ( e x c = e x c ,   c o u n t d o w n = 3 0   *   ( s e l f . r e q u e s t . r e t r i e s   +   1 ) )   f r o m   e x c  
 