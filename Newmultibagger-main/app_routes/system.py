import asyncio
import json
import os
import sys
from pathlib import Path

from modules.auth import get_api_key
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import FileResponse, JSONResponse

from modules.cache import (
    _cache_is_fresh,
    _cache_set,
    movers_cache,
    movers_cache_lock,
)
from modules.dependencies import refresh_prices_once
from modules.ws_auth import issue_ws_token, verify_ws_token, ws_reject
from core.observability.logger import get_logger
from modules.rate_limit import limiter

api_logger = get_logger("sovereign.api")

router = APIRouter()
_price_refresh_task: asyncio.Task | None = None
_SIGNALS_FILE = Path(__file__).resolve().parent.parent / "paper_trade_signals.json"

# Per-IP connection cap — prevents a single client from flooding the worker.
_WS_MAX_CONNS_PER_IP = int(os.getenv("WS_MAX_CONNS_PER_IP", "5"))
_ws_ip_counts: dict[str, int] = {}


# ── WebSocket helpers ─────────────────────────────────────────────────────────


def _ws_client_ip(websocket: WebSocket) -> str:
    """Best-effort client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = websocket.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return websocket.client.host if websocket.client else "unknown"


def _ws_ip_acquire(ip: str) -> bool:
    """Return True and increment counter if the IP is under the cap."""
    count = _ws_ip_counts.get(ip, 0)
    if count >= _WS_MAX_CONNS_PER_IP:
        return False
    _ws_ip_counts[ip] = count + 1
    return True


def _ws_ip_release(ip: str) -> None:
    count = _ws_ip_counts.get(ip, 1)
    if count <= 1:
        _ws_ip_counts.pop(ip, None)
    else:
        _ws_ip_counts[ip] = count - 1


# ── Token issuance ────────────────────────────────────────────────────────────


@router.get("/api/ws-token")
async def get_ws_token(api_key: str = Depends(get_api_key)):
    """Issue a short-lived WebSocket connect token.

    The frontend must call this endpoint (with its normal X-API-Key header)
    before opening a /ws/prices connection.  The returned ``token`` is
    passed as a query-string parameter::

        ws://host/ws/prices?token=<token>

    Tokens expire after WS_TOKEN_TTL_SECONDS (default: 60 s) and are
    single-purpose — they cannot be used as an API key substitute.
    """
    try:
        token = issue_ws_token(consumer="browser")
        return {"token": token, "ttl_seconds": int(os.getenv("WS_TOKEN_TTL_SECONDS", "60"))}
    except RuntimeError as exc:
        api_logger.error("WS token issuance failed — WS_TOKEN_SECRET not set", error=str(exc))
        return JSONResponse(
            status_code=503,
            content={"detail": "WebSocket token service not configured. Set WS_TOKEN_SECRET."},
        )


# ── WebSocket endpoints ───────────────────────────────────────────────────────


@router.websocket("/ws/signals")
async def websocket_signals(websocket: WebSocket, api_key: str = Depends(get_api_key)):
    """Real-time signal broadcast via websocket."""
    from modules.dependencies import manager
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()   # keep-alive, disconnect detection
    except WebSocketDisconnect:
        api_logger.info("Signal websocket client disconnected")
        manager.disconnect(websocket)
    except Exception as e:
        api_logger.error("Signal websocket error", error=str(e))
        manager.disconnect(websocket)


@router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket):
    """Real-time price feed — multi-worker safe via Redis Pub/Sub.

    Auth: short-lived token issued by GET /api/ws-token, passed as
    ``?token=<token>`` query parameter.  Rejects with close 1008 on
    missing, expired, or tampered tokens.

    Connection cap: at most WS_MAX_CONNS_PER_IP (default 5) concurrent
    connections per client IP.  Excess connections are closed with 1008.
    """
    from modules.dependencies import manager

    # ── 1. Token verification ─────────────────────────────────────────────────
    token = websocket.query_params.get("token")
    if not verify_ws_token(token):
        api_logger.warning(
            "WS /ws/prices rejected — invalid or missing token",
            client=str(websocket.client),
        )
        await ws_reject(websocket, code=1008, reason="Unauthorized — obtain a token from /api/ws-token")
        return

    # ── 2. Per-IP connection cap ──────────────────────────────────────────────
    client_ip = _ws_client_ip(websocket)
    if not _ws_ip_acquire(client_ip):
        api_logger.warning(
            "WS /ws/prices rejected — connection cap reached",
            ip=client_ip,
            cap=_WS_MAX_CONNS_PER_IP,
        )
        await ws_reject(websocket, code=1008, reason="Too many connections from this IP")
        return

    # ── 3. Accept and keep alive ──────────────────────────────────────────────
    await manager.connect(websocket)
    try:
        while True:
            # The connection is kept alive here.
            # Outbound messages are pushed asynchronously by manager.broadcast()
            # which is called from the Redis Pub/Sub listener task started in
            # main.py lifespan (manager.listen_pubsub).
            await websocket.receive_text()
    except WebSocketDisconnect:
        api_logger.info("Price websocket client disconnected", ip=client_ip)
    except Exception as e:
        api_logger.error("Price websocket error", error=str(e), ip=client_ip)
    finally:
        manager.disconnect(websocket)
        _ws_ip_release(client_ip)


# ── REST endpoints ────────────────────────────────────────────────────────────


@router.post("/api/scan")
@limiter.limit("2/minute")
async def run_scan(request: Request):
    """Trigger full market scan."""
    try:
        from worker.task_bus import dispatch
        from worker.tasks import run_full_scan

        task_id = await dispatch(run_full_scan, _task_options={"queue": "screening"})
        return {"status": "scan_initiated", "task_id": task_id, "mode": "async"}
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
        metrics: dict = {"status": "success"}
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
