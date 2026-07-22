# worker/tasks.py
"""
Sovereign AI Trading Engine v4.0 — Celery Task Definitions
Patched: all tasks decorated with celery_task_timer for Prometheus metrics.
All logging via SovereignLogger (structured JSON + console).
"""

import os
import sys
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
        from modules.data_layer.data_service import get_data_manager
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
    """Retrain the XGBoost meta-model.

    Delegates to run_automated_training() (not train_hybrid_model() directly)
    so that:
      1. Bootstrap fallback fires when PIT data is insufficient.
      2. Training metadata is recorded to ml_metadata.
      3. Walk-forward metrics are captured in the return value.
    """
    try:
        from modules.ml_ops import run_automated_training
        from modules.hybrid_scoring import load_walk_forward_report

        success = run_automated_training()
        wf = load_walk_forward_report() or {}

        if success:
            try:
                import json
                from pathlib import Path
                windows = wf.get("windows", [])
                if windows:
                    ic_summary = {
                        "overall": round(wf.get("spearman_ic") or 0.0, 4),
                        "folds": len(windows),
                        "note": "regime-split requires pred_df; using overall fold IC",
                    }
                    cache_path = Path("runtime/regime_ic_cache.json")
                    cache_path.parent.mkdir(exist_ok=True)
                    cache_path.write_text(json.dumps({
                        "ic_by_regime": ic_summary,
                        "folds": len(windows),
                        "updated_at": datetime.now().isoformat(),
                    }))
                    logger.info("ic_cache.updated", ic_by_regime=ic_summary)
            except Exception as exc:
                logger.warning("ic_cache.update_failed", error=str(exc))
        return {
            "status": "success" if success else "skipped",
            "retrained_at": datetime.now().isoformat(),
            "wf_status": wf.get("status"),
            "spearman_ic": wf.get("spearman_ic"),
            "hit_rate": wf.get("hit_rate"),
            "folds": wf.get("folds"),
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


@app.task(name="worker.tasks.check_all_thesis_breaks", time_limit=300)
@celery_task_timer("check_all_thesis_breaks")
def check_all_thesis_breaks_task():
    """
    Scan every open position for thesis breaks and persist results to
    thesis_break.json so /api/thesis_break returns live data.

    Scheduled: weekday mornings before market open (08:00 IST).
    """
    from modules.tracking.thesis_monitor import check_all_thesis_breaks
    import json
    from pathlib import Path

    breaks = check_all_thesis_breaks()
    payload = {"items": breaks, "count": len(breaks)}
    Path("thesis_break.json").write_text(json.dumps(payload))
    logger.info("thesis_break_scan.complete", breaks_found=len(breaks))
    return payload


@app.task(name="worker.tasks.refresh_regime_cache")
@celery_task_timer("refresh_regime_cache")
def refresh_regime_cache():
    try:
        from modules.data_layer.data_service import MarketDataProvider

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


@app.task(name="worker.tasks.refresh_stale_data", bind=True,
          max_retries=2, default_retry_delay=60)
@celery_task_timer("refresh_stale_data")
def refresh_stale_data(self, symbol: str):
    try:
        from modules.data_layer.data_service import get_data_manager
        from modules.data_utils import run_coroutine_sync
        dm = get_data_manager()
        run_coroutine_sync(dm.async_fetch_fundamentals(symbol))
        logger.info("Stale data refreshed", symbol=symbol)
    except Exception as exc:
        logger.warning("refresh_stale_data failed", symbol=symbol, error=str(exc))
        raise self.retry(exc=exc) from exc


@app.task(name="worker.tasks.batch_ml_inference", time_limit=600)
@celery_task_timer("batch_ml_inference")
def batch_ml_inference():
    """Re-score every stock in multibaggers with the current XGBoost model.

    Writes ml_predicted_return, shap_breakdown, shap_top_drivers back to DB.
    No-ops gracefully when the model has not been trained yet.
    """
    try:
        from modules.hybrid_scoring import model_is_trained

        if not model_is_trained():
            logger.info(
                "batch_ml_inference.skipped",
                reason="model not trained — run retrain_xgboost first",
            )
            return {"status": "skipped", "reason": "model_not_trained"}

        from modules.data_layer.data_utils import run_coroutine_sync
        from modules.ml_ops import batch_update_multibaggers_ml

        run_coroutine_sync(batch_update_multibaggers_ml())

        logger.info("batch_ml_inference.completed", updated_at=datetime.now().isoformat())
        return {"status": "success", "completed_at": datetime.now().isoformat()}

    except Exception as exc:
        logger.error("batch_ml_inference.failed", error=str(exc))
        return {"status": "error", "message": str(exc)}

@app.task(name="worker.tasks.check_factor_data_freshness", time_limit=60)
def check_factor_data_freshness():
    """Check India factor returns CSV freshness and fire a DATA_STALE webhook
    if the file is missing or older than FACTOR_STALENESS_DAYS (default 45).

    Runs nightly. If stale, publishes a DATA_STALE event via dispatch_alerts()
    so any webhook subscriber watching DATA_STALE receives the alert.
    Also logs a _log.critical() so the structured log triggers PagerDuty /
    Slack alerting via the ops log pipeline.
    """
    from modules.india_factor_loader import (
        factor_returns_are_stale,
        FACTOR_CSV_PATH,
        FACTOR_COLUMNS,
    )
    import asyncio
    import os
    from datetime import date

    max_age = int(os.getenv("FACTOR_STALENESS_DAYS", "45"))
    stale = factor_returns_are_stale(max_age_days=max_age)

    if not stale:
        logger.info(
            "factor_data_fresh",
            csv=str(FACTOR_CSV_PATH),
            max_age_days=max_age,
        )
        return {"status": "fresh"}

    # ── 1. Structured log at CRITICAL so it triggers ops alerting ────────────
    csv_exists = FACTOR_CSV_PATH.exists()
    if csv_exists:
        import pandas as pd
        df = pd.read_csv(FACTOR_CSV_PATH)
        last_date = df["date"].max() if not df.empty else "unknown"
        age_days = (date.today() - date.fromisoformat(str(last_date))).days
        msg = (
            f"India factor returns are {age_days} days old "
            f"(last: {last_date}, threshold: {max_age}d). "
            f"Run: python scripts/build_india_factors.py --update"
        )
        missing_cols = [c for c in FACTOR_COLUMNS if c not in df.columns]
        detail = {
            "last_date": str(last_date),
            "age_days": age_days,
            "threshold_days": max_age,
            "csv_path": str(FACTOR_CSV_PATH),
            "missing_columns": missing_cols,
        }
    else:
        msg = (
            f"India factor returns CSV not found at {FACTOR_CSV_PATH}. "
            f"Run: python scripts/build_india_factors.py"
        )
        detail = {
            "csv_path": str(FACTOR_CSV_PATH),
            "age_days": None,
            "threshold_days": max_age,
            "missing_columns": FACTOR_COLUMNS,
        }

    logger.critical("factor_data_stale", message=msg, **detail)

    # ── 2. Webhook dispatch (DATA_STALE event) ────────────────────────────────
    alert_payload = [
        {
            "type": "DATA_STALE",
            "severity": "high",
            "source": "factor_data_check",
            "message": msg,
            **detail,
        }
    ]
    try:
        asyncio.run(_dispatch_factor_alert(alert_payload))
    except RuntimeError:
        # Already inside an event loop (e.g. during testing) — use nest_asyncio
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(
            _dispatch_factor_alert(alert_payload)
        )
    except Exception as exc:
        logger.error("factor_data_stale_webhook_failed", error=str(exc))

    return {"status": "stale", **detail}


async def _dispatch_factor_alert(alerts: list[dict]) -> None:
    """Thin async wrapper so the sync Celery task can call dispatch_alerts."""
    try:
        from modules.webhook_dispatcher import dispatch_alerts
        await dispatch_alerts(alerts)
    except Exception as exc:
        logger.error("dispatch_alerts_failed", error=str(exc))
