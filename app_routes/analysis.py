from fastapi import APIRouter, HTTPException
from datetime import datetime
import csv
import json
import os
import pandas as pd
import modules.dependencies as deps
from modules.symbol_utils import normalize_symbol
from modules.drift_monitor import monitor_drift

router = APIRouter()


def _read_json_file(path: str):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_rejections_csv(path: str, limit: int = 20):
    with open(path, "r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return list(reversed(rows[-limit:]))

@router.get("/api/liquidity")
async def get_liquidity_forensics():
    """Fetch stocks with suspicious liquidity-to-volatility ratios"""
    try:
        if os.path.exists("liquidity.json"):
            return _read_json_file("liquidity.json")
        return await deps._run_blocking(deps._read_records, "SELECT * FROM liquidity_forensics ORDER BY score DESC")
    except Exception as e: return {"error": str(e)}

@router.get("/api/recovery")
async def get_drawdown_recovery():
    """Fetch stocks showing V-shaped recovery from 52W lows"""
    try:
        if os.path.exists("recovery.json"):
            return _read_json_file("recovery.json")
        return await deps._run_blocking(deps._read_records, "SELECT * FROM recovery_plays ORDER BY score DESC")
    except Exception as e: return {"error": str(e)}

@router.get("/api/rejections")
async def get_rejection_logs():
    """Fetch recent trade rejections by the Risk Governor"""
    try:
        if os.path.exists("rejected_trades.csv"):
            return _read_rejections_csv("rejected_trades.csv")
        if os.path.exists(os.path.join("logs", "rejected_trades.csv")):
            return _read_rejections_csv(os.path.join("logs", "rejected_trades.csv"), limit=50)
        return await deps._run_blocking(deps._read_records, "SELECT * FROM trade_rejections ORDER BY timestamp DESC LIMIT 50")
    except Exception as e: return {"error": str(e)}

@router.get("/api/thesis_break")
async def get_thesis_breaks():
    """Fetch stocks where the fundamental investment thesis has potentially broken"""
    try:
        if os.path.exists("thesis_break.json"):
            payload = _read_json_file("thesis_break.json")
            if isinstance(payload, dict):
                return {"status": "success", **payload}
            return {"status": "success", "items": payload}
        return await deps._run_blocking(deps._read_records, "SELECT * FROM thesis_breaks ORDER BY severity DESC, detected_at DESC")
    except Exception as e: return {"error": str(e)}

@router.get("/api/revisions/{symbol}")
async def get_revisions(symbol: str):
    """Fetch analyst recommendations trend and score impact."""
    try:
        from modules.revisions import analyze_revisions
        import yfinance as yf
        symbol = normalize_symbol(symbol)
        ticker = yf.Ticker(symbol)
        score_impact, sentiment = await deps._run_blocking(analyze_revisions, ticker)
        return {"symbol": symbol, "score_impact": score_impact, "sentiment": sentiment, "timestamp": datetime.now().isoformat()}
    except Exception as e: return {"error": str(e)}

@router.get("/api/drift/{symbol}")
async def get_drift(symbol: str):
    """Detect investment thesis drift for a single stock."""
    try:
        symbol = normalize_symbol(symbol)
        def _fetch_drift_data():
            conn = deps.get_connection()
            try:
                row = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
                return row.iloc[0].to_dict() if not row.empty else None
            finally: conn.close()
        
        stock_data = await deps._run_blocking(_fetch_drift_data)
        if not stock_data: raise HTTPException(status_code=404, detail="Stock not found")
        status, reason = monitor_drift(stock_data)
        return {"symbol": symbol, "status": status, "reason": reason, "timestamp": datetime.now().isoformat()}
    except Exception as e: return {"error": str(e)}
