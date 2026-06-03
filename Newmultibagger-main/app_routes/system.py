import asyncio
import json
import os
import sys

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from modules.cache import (
    _cache_is_fresh,
    _cache_set,
    movers_cache,
    movers_cache_lock,
)
from modules.dependencies import refresh_prices_once
from modules.structured_logger import SovereignLogger
from modules.rate_limit import limiter

api_logger = SovereignLogger("sovereign.api")

router = APIRouter()
_price_refresh_task: asyncio.Task | None = None


@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """Real-time signal broadcast via websocket."""
    await websocket.accept()
    try:
        while True:
            # Broadcast the latest paper trade signals from disk cache.
            if os.path.exists("paper_trade_signals.json"):
                with open("paper_trade_signals.json") as f:
                    signals = json.load(f)
                await websocket.send_json(signals)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        api_logger.info("Signal websocket client disconnected")
    except Exception as e:
        api_logger.error("Signal websocket error", error=str(e))


@router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    """Real-time price feed broadcast via websocket (Multi-worker safe)."""
    from modules.dependencies import manager
    await manager.connect(websocket)
    try:
        while True:
            # Keep client connection open. Messages are broadcast asynchronously.
            await websocket.receive_text()
    except WebSocketDisconnect:
        api_logger.info("Price websocket client disconnected")
    except Exception as e:
        api_logger.error("Price websocket error", error=str(e))
    finally:
        manager.disconnect(websocket)


@router.post("/api/scan")
@limiter.limit("2/minute")
async def run_scan(request: Request):
    """Trigger full market scan."""
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            os.path.join("scripts", "internal", "screener.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return {"status": "scan_initiated", "pid": process.pid}
    except Exception as e:
        return {"error": str(e)}


@router.post("/api/refresh-prices")
@limiter.limit("3/minute")
async def refresh_prices(request: Request):
    """Start one market-data refresh cycle for prices and swing tactical fields."""
    global _price_refresh_task

    if _price_refresh_task is not None and not _price_refresh_task.done():
        return {"status": "running"}

    _price_refresh_task = asyncio.create_task(refresh_prices_once())
    return {"status": "started"}


@router.get("/api/refresh-prices")
async def refresh_prices_status():
    """Return status for the latest one-shot market-data refresh cycle."""
    if _price_refresh_task is None:
        return {"status": "idle"}
    if not _price_refresh_task.done():
        return {"status": "running"}

    error = _price_refresh_task.exception()
    if error is not None:
        return {"status": "failed", "error": str(error)}
    return {"status": "completed"}


@router.get("/")
def read_root():
    """Serve the Brutalist Terminal UI"""
    from pathlib import Path
    project_root = Path(__file__).resolve().parents[1]
    return FileResponse(project_root / "web-ui" / "index.html")


@router.get("/api/market_movers")
async def get_market_movers():
    """Placeholder for Top Gainers/Losers"""
    try:
        if _cache_is_fresh(movers_cache, 3600):
            return movers_cache["payload"]
        async with movers_cache_lock:
            payload = {"gainers": [], "losers": [], "active": [], "_status": "not_implemented"}
            _cache_set(movers_cache, payload)
            return payload
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/backtest-metrics")
@limiter.limit("10/minute")
async def get_backtest_metrics(request: Request):
    """Aggregate backtesting metrics from reports."""
    try:
        if not os.path.exists("backtest_report.md"):
            return {"status": "pending"}
        metrics = {"status": "success"}
        with open("backtest_report.md", encoding="utf-8") as f:
            for line in f:
                if "Average CAGR" in line:
                    metrics["cagr"] = line.split(":")[-1].replace("*", "").replace("%", "").strip()
                elif "Win Rate" in line:
                    metrics["win_rate"] = (
                        line.split(":")[-1].replace("*", "").replace("%", "").strip()
                    )
                elif "Max Drawdown" in line:
                    metrics["max_dd"] = (
                        line.split(":")[-1].replace("*", "").replace("%", "").strip()
                    )
                elif "Sharpe Ratio" in line:
                    metrics["sharpe"] = line.split(":")[-1].replace("*", "").strip()
        return metrics
    except Exception as e:
        return {"error": str(e)}
