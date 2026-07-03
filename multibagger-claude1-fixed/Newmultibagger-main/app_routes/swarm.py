from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime

import pandas as pd
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from db.db_core import execute_sql
from modules.alerts import AlertEngine
from modules.auth import get_api_key
from modules.webhook_dispatcher import dispatch_alerts
from core.observability.logger import get_logger

router = APIRouter(prefix="/swarm", tags=["swarm"])
_log = get_logger("sovereign.swarm")

RUFLO_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../services/ruflo-orchestrator")
)

_alert_engine = AlertEngine()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _load_portfolio() -> pd.DataFrame:
    """Load open positions from multibaggers as a minimal portfolio frame.

    AlertEngine.check_portfolio() needs: Symbol, Entry_Price, Stop_Loss.
    We map multibaggers.buy_below → Entry_Price and stop_loss_atr → Stop_Loss
    as the best proxies available without a dedicated positions table.
    """
    rows = execute_sql(
        """
        SELECT symbol        AS Symbol,
               buy_below     AS Entry_Price,
               stop_loss_atr AS Stop_Loss
        FROM   multibaggers
        WHERE  score >= 70
        """,
        fetch_all=True,
    )
    if not rows:
        return pd.DataFrame(columns=["Symbol", "Entry_Price", "Stop_Loss"])
    df = pd.DataFrame(rows)
    df["Entry_Price"] = pd.to_numeric(df["Entry_Price"], errors="coerce").fillna(0)
    df["Stop_Loss"] = pd.to_numeric(df["Stop_Loss"], errors="coerce").fillna(0)
    return df


def _load_current_prices() -> dict[str, float]:
    """Current price snapshot from multibaggers."""
    rows = execute_sql(
        "SELECT symbol, price FROM multibaggers WHERE price IS NOT NULL",
        fetch_all=True,
    )
    return {r["symbol"]: float(r["price"]) for r in (rows or []) if r.get("price")}


def _load_current_scores() -> dict[str, float]:
    """Current score snapshot from multibaggers."""
    rows = execute_sql(
        "SELECT symbol, score FROM multibaggers WHERE score IS NOT NULL",
        fetch_all=True,
    )
    return {r["symbol"]: float(r["score"]) for r in (rows or []) if r.get("score")}


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/status")
async def get_swarm_status():
    """Proxy swarm status from Ruflo microservice."""
    import sys
    # npx.cmd is Windows-only; use "npx" on Linux/macOS
    npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
    try:
        result = subprocess.run(
            [npx_cmd, "ruflo", "swarm", "status", "--format", "json"],
            cwd=RUFLO_DIR,
            capture_output=True,
            text=True,
            shell=True,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
        return {"status": "offline", "error": result.stderr}
    except Exception as e:
        # Use "error" key to match SwarmStatusResponse contract (not "message")
        return {"status": "error", "error": str(e)}


@router.get("/alerts")
async def get_swarm_alerts(_api_key: str = Depends(get_api_key)):
    """Run AlertEngine against live portfolio and dispatch results to webhooks.

    Returns the alerts that were generated.  Webhook fan-out happens
    asynchronously in the background — the HTTP response does not wait
    for subscriber acknowledgements.
    """
    try:
        portfolio = _load_portfolio()
        prices = _load_current_prices()
        scores = _load_current_scores()

        alerts = _alert_engine.check_portfolio(portfolio, prices, scores)

        if alerts:
            # Fan-out to all active webhook subscribers — non-blocking.
            # We await here so the log entries are written before we respond,
            # but httpx timeouts (5 s each) are already capped inside
            # dispatch_alerts, so total latency is bounded.
            try:
                await dispatch_alerts(alerts)
            except Exception as exc:
                _log.error("Webhook dispatch error (non-fatal)", error=str(exc))

        _log.info(
            "Swarm alert scan complete",
            portfolio_size=len(portfolio),
            alerts_generated=len(alerts),
        )
        return {
            "scanned_at": datetime.now(UTC).isoformat(),
            "portfolio_size": len(portfolio),
            "alerts": alerts,
        }

    except Exception as exc:
        _log.error("Swarm alert scan failed", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"error": str(exc), "alerts": []},
        )
