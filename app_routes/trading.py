from fastapi import APIRouter, HTTPException
import modules.dependencies as deps
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime
from modules.retry_utils import run_with_exponential_backoff
from modules.allocation_hrp import HRPAllocator

router = APIRouter()

@router.post("/api/order")
async def place_order(order: deps.OrderRequest):
    """Order lifecycle endpoint for paper execution (BUY/SELL)."""
    try:
        symbol = order.symbol.strip().upper()
        side = order.side.strip().upper()

        if not symbol: return {"status": "rejected", "error": "symbol is required"}
        if side not in {"BUY", "SELL"}: return {"status": "rejected", "error": "side must be BUY or SELL"}
        if "." not in symbol: symbol = f"{symbol}.NS"

        if side == "BUY":
            # Risk Gates: Kill Switch & VaR
            vix = order.current_vix if order.current_vix is not None else 0.0
            is_safe, msg = deps.risk_governor.check_kill_switch(vix, drawdown_rate_weekly=order.drawdown_rate_weekly)
            if not is_safe:
                deps.risk_governor.log_rejected_trade(symbol, msg, order.price)
                return {"status": "rejected", "side": side, "symbol": symbol, "reason": msg}

            var_safe, var_msg = deps.risk_governor.validate_var_budget(order.projected_var_pct, order.max_var_pct)
            if not var_safe: return {"status": "rejected", "side": side, "symbol": symbol, "reason": var_msg}

            # Correlation gate
            adj_qty = order.quantity
            if order.portfolio_correlation is not None:
                factor = deps.risk_governor.validate_correlation_risk(order.portfolio_correlation)
                if factor <= 0: return {"status": "rejected", "side": side, "symbol": symbol, "reason": "Correlation emergency de-risk"}
                adj_qty = max(1, int(round(order.quantity * factor)))

            result = await deps._run_blocking(deps.portfolio_tracker.log_entry, symbol, order.price, order.score, adj_qty)
            
            # Thesis record
            if result.get("status") != "rejected":
                try:
                    from modules.thesis_monitor import record_buy_thesis
                    def _get_snapshot():
                        conn = deps.get_connection()
                        try:
                            row = pd.read_sql("SELECT * FROM multibaggers WHERE symbol = ?", conn, params=(symbol,))
                            return row.iloc[0].to_dict() if not row.empty else {}
                        finally: conn.close()
                    snap = await deps._run_blocking(_get_snapshot)
                    if snap: await deps._run_blocking(record_buy_thesis, symbol, snap, order.score, 0, "SIDEWAYS")
                except: pass
        else:
            result = await deps._run_blocking(deps.portfolio_tracker.log_exit, symbol, order.price, order.reason)

        if result.get("status") == "rejected":
            deps.risk_governor.log_rejected_trade(symbol, result.get("reason", "Order rejected"), order.price)

        return {
            "status": result.get("status", "accepted"), "side": side, "symbol": symbol,
            "quantity": adj_qty if side == "BUY" else order.quantity, "price": order.price,
            "reason": result.get("reason", order.reason), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e: return {"status": "error", "error": str(e)}

@router.get("/api/trades/open")
async def get_open_trades():
    try:
        df = await deps._run_blocking(deps.portfolio_tracker.get_open_positions)
        return df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None}).to_dict(orient="records") if not df.empty else []
    except Exception as e: return {"error": str(e)}

@router.get("/api/trades/history")
async def get_trade_history():
    try:
        df = await deps._run_blocking(deps.portfolio_tracker.get_trade_history)
        return df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None}).to_dict(orient="records") if not df.empty else []
    except Exception as e: return {"error": str(e)}

@router.get("/api/allocation/hrp")
@router.get("/api/hrp")
async def get_hrp_allocation():
    """Calculate HRP weights for top 15 stocks"""
    try:
        def _get_symbols():
            conn = deps.get_connection()
            try: return pd.read_sql("SELECT symbol FROM multibaggers ORDER BY score DESC LIMIT 15", conn)["symbol"].tolist()
            finally: conn.close()
        symbols = await deps._run_blocking(_get_symbols)
        if not symbols: raise HTTPException(status_code=404, detail="No stocks found")
        
        data = await run_with_exponential_backoff(lambda: deps._run_ticker_blocking(yf.download, symbols, period="1y", interval="1d", progress=False, auto_adjust=True), context="hrp price fetch")
        if data.empty: raise HTTPException(status_code=502, detail="Failed to fetch data")
        prices = data["Close"] if "Close" in data else data.xs('Close', axis=1, level=0)
        returns = prices.pct_change().dropna(how='all').fillna(0)
        # Black Zone Gate: Halt allocation if market is in total kill-switch mode
        zone, cap = deps.risk_governor.get_regime_zone(data["Close"].iloc[-1] if "Close" in data else 0.0) # Placeholder, need real VIX
        # Actually, let's fetch real VIX from the regime cache
        regime_data = await deps._run_blocking(deps.regime_cache.get, "payload")
        if regime_data:
            current_vix = regime_data.get('vix', 0.0)
            zone, cap = deps.risk_governor.get_regime_zone(current_vix)
            if zone == "BLACK":
                 return {"error": "HRP ALLOCATION HALTED: Market is in BLACK zone (VIX > 35). High probability of capital destruction.", "weights": {}, "timestamp": datetime.now().isoformat()}

        weights = HRPAllocator().allocate(returns)
        return {"weights": {k: float(v) for k, v in sorted(weights.items(), key=lambda x: x[1], reverse=True)}, "timestamp": datetime.now().isoformat()}
    except Exception as e: return {"error": str(e)}

@router.get("/api/slippage_stats")
async def get_slippage_stats():
    """Execution Quality Metrics (Slippage Calibration)"""
    try:
        data = await deps._run_blocking(deps._read_records, "SELECT * FROM slippage_metrics ORDER BY tier")
        return deps._json_safe_clean(data)
    except Exception as e: return {"error": str(e)}
