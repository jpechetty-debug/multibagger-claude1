from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
import asyncio
import os
import sys
import json
import modules.dependencies as deps

router = APIRouter()

@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket):
    """Real-time signal broadcast via websocket."""
    await websocket.accept()
    try:
        while True:
            # Broadcast the latest paper trade signals from disk cache.
            if os.path.exists("paper_trade_signals.json"):
                with open("paper_trade_signals.json", "r") as f:
                    signals = json.load(f)
                await websocket.send_json(signals)
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        deps.api_logger.info("Signal websocket client disconnected")
    except Exception as e:
        deps.api_logger.error("Signal websocket error", error=str(e))

@router.post("/api/scan")
async def run_scan():
    """Trigger full market scan (screener.py)"""
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "screener.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        return {"status": "scan_initiated", "pid": process.pid}
    except Exception as e: return {"error": str(e)}

@router.get("/")
def read_root():
    """Serve the Brutalist Terminal UI"""
    return FileResponse("web-ui/index.html")

@router.get("/api/market_movers")
async def get_market_movers():
    """Placeholder for Top Gainers/Losers"""
    try:
        if deps._cache_is_fresh(deps.movers_cache, 3600):
            return deps.movers_cache["payload"]
        async with deps.movers_cache_lock:
            payload = {"gainers": [], "losers": [], "active": [], "_status": "not_implemented"}
            deps._cache_set(deps.movers_cache, payload)
            return payload
    except Exception as e: return {"error": str(e)}

@router.get("/api/backtest-metrics")
async def get_backtest_metrics():
    """Aggregate backtesting metrics from reports."""
    try:
        if not os.path.exists("backtest_report.md"): return {"status": "pending"}
        metrics = {"status": "success"}
        with open("backtest_report.md", "r", encoding="utf-8") as f:
            for line in f:
                if "Average CAGR" in line: metrics["cagr"] = line.split(":")[-1].replace("*","").replace("%","").strip()
                elif "Win Rate" in line: metrics["win_rate"] = line.split(":")[-1].replace("*","").replace("%","").strip()
                elif "Max Drawdown" in line: metrics["max_dd"] = line.split(":")[-1].replace("*","").replace("%","").strip()
                elif "Sharpe Ratio" in line: metrics["sharpe"] = line.split(":")[-1].replace("*","").strip()
        return metrics
    except Exception as e: return {"error": str(e)}
