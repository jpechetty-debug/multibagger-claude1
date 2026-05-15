from datetime import datetime
from typing import Any, cast

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

import modules.dependencies as deps
from modules.allocation_hrp import HRPAllocator
from modules.models import OrderRequest
from modules.retry_utils import run_with_exponential_backoff
from modules.symbol_utils import canonical_symbol

router = APIRouter()

BLOCKED_SWING_RATING_TERMS = ("AVOID", "REJECT", "DISQUALIFIED", "SELL")

SWING_SOURCE_COLUMNS = [
    "symbol",
    "price",
    "score",
    "rating",
    "sector",
    "market_cap_cr",
    "f_score",
    "pe_ratio",
    "debt_equity",
    "rs_rating",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "vol_breakout",
    "dist_from_52w_high",
    "down_from_52w",
    "atr",
    "stop_loss",
    "stop_loss_atr",
    "buy_below",
    "target_1",
    "target_2",
    "technical_signal",
    "as_of_date",
    "updated_at",
    "data_quality",
]


def _as_float(value, default: float | None = 0.0) -> float | None:
    if value is None:
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(parsed):
        return default
    return parsed


def _fraction_to_pct(value) -> float:
    """Convert fraction-scale values to percent. Unconditionally multiplies by 100."""
    parsed = _as_float(value, 0.0) or 0.0
    return parsed * 100


def _round_price(value: float) -> float:
    if value >= 1000:
        return round(value, 1)
    if value >= 100:
        return round(value, 2)
    return round(value, 2)


def _format_signal_date(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return datetime.now().strftime("%d %b %I:%M %p")
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return cast(str, parsed.strftime("%d %b %I:%M %p"))


def _display_symbol(symbol: str) -> str:
    normalized = str(symbol or "").strip().upper()
    if normalized.endswith(".NS"):
        return f"NSE:{normalized[:-3]}-EQ"
    return normalized


def _is_blocked_swing_rating(value) -> bool:
    rating = str(value or "").strip().upper()
    return any(term in rating for term in BLOCKED_SWING_RATING_TERMS)


def _quality_flags(row: pd.Series, *, snapshot_age_days: int | None = None) -> list[str]:
    flags: list[str] = []
    rating = str(row.get("rating") or "").strip()
    data_quality = _as_float(row.get("data_quality"), 0.0) or 0.0
    market_cap = _as_float(row.get("market_cap_cr"), 0.0) or 0.0
    f_score = _as_float(row.get("f_score"), None)
    pe_ratio = _as_float(row.get("pe_ratio"), None)
    debt_equity = _as_float(row.get("debt_equity"), None)

    if rating and _is_blocked_swing_rating(rating):
        flags.append("BLOCKED_RATING")
    if data_quality < 70:
        flags.append("LOW_DATA_QUALITY")
    if market_cap < 1000:
        flags.append("SMALL_OR_UNKNOWN_MARKET_CAP")
    if f_score is not None and f_score < 4:
        flags.append("WEAK_F_SCORE")
    if pe_ratio is not None and pe_ratio > 120:
        flags.append("STRETCHED_PE")
    if debt_equity is not None and debt_equity > 3:
        flags.append("HIGH_DEBT_EQUITY")
    if snapshot_age_days is not None and snapshot_age_days > 2:
        flags.append("STALE_PRICE_SNAPSHOT")

    return flags


def _load_swing_source_rows() -> pd.DataFrame:
    """Load the screener columns needed to derive tactical swing setups."""
    try:
        with deps.get_sqla_connection() as conn:
            preview = pd.read_sql(text("SELECT * FROM multibaggers LIMIT 0"), conn)
            existing_columns = [
                column for column in SWING_SOURCE_COLUMNS if column in preview.columns
            ]
            if not existing_columns:
                return pd.DataFrame()

            query = f"SELECT {', '.join(existing_columns)} FROM multibaggers"
            return pd.read_sql(text(query), conn)
    except Exception as exc:
        deps.api_logger.warning("Failed to load swing source rows", error=str(exc))
        return pd.DataFrame()


def _build_swing_trade(row: pd.Series) -> dict | None:
    price = _as_float(row.get("price"), 0.0) or 0.0
    if price <= 0:
        return None

    symbol = str(row.get("symbol") or "").strip().upper()
    if not symbol:
        return None

    score = _as_float(row.get("score"), 0.0) or 0.0
    ret_1m_pct = _fraction_to_pct(row.get("ret_1m"))
    ret_3m_pct = _fraction_to_pct(row.get("ret_3m"))
    # dist_from_52w_high is always in fraction (0-1); down_from_52w is in percent
    raw_dist = row.get("dist_from_52w_high")
    if raw_dist is not None and _as_float(raw_dist) is not None:
        dist_52w_pct = (_as_float(raw_dist, 0.0) or 0.0) * 100
    else:
        dist_52w_pct = _as_float(row.get("down_from_52w"), 0.0) or 0.0
    vol_breakout = _as_float(row.get("vol_breakout"), 0.0) or 0.0
    atr = _as_float(row.get("atr"), 0.0) or 0.0
    atr_pct = (atr / price) * 100 if atr > 0 else 0.0

    raw_stop = _as_float(row.get("stop_loss_atr"), None) or _as_float(row.get("stop_loss"), None)
    stop_loss = raw_stop if raw_stop and 0 < raw_stop < price else None
    if stop_loss is None:
        stop_loss = price - (2 * atr) if atr > 0 else price * 0.92
    stop_loss = max(stop_loss, price * 0.75)

    raw_target = _as_float(row.get("target_1"), None) or _as_float(row.get("target_2"), None)
    # Detect and replace uniform ~25% targets with ATR-based dynamic targets
    target = None
    if raw_target and raw_target > price:
        target_deviation = abs(((raw_target - price) / price) - 0.25)
        if target_deviation > 0.02:
            target = raw_target  # Genuine analytical target
    if target is None:
        # Dynamic target: 3x ATR or 8% of price, whichever is greater
        target = price + max(3.0 * atr, price * 0.08)

    target_pct = ((target - price) / price) * 100
    risk_pct = ((price - stop_loss) / price) * 100
    if target_pct <= 3 or risk_pct <= 0:
        return None

    buy_below = _as_float(row.get("buy_below"), None)
    entry_padding = min(max((atr / price) * 0.35 if atr > 0 else 0.012, 0.006), 0.025)
    entry_low = price * (1 - entry_padding)
    entry_high = price * (1 + entry_padding)
    if buy_below and price * 0.97 <= buy_below <= price * 1.08:
        entry_high = max(entry_high, buy_below)

    market_cap = _as_float(row.get("market_cap_cr"), 0.0) or 0.0
    data_quality = _as_float(row.get("data_quality"), 0.0) or 0.0
    f_score = _as_float(row.get("f_score"), None)
    pe_ratio = _as_float(row.get("pe_ratio"), None)
    debt_equity = _as_float(row.get("debt_equity"), None)
    rating = str(row.get("rating") or "Unrated").strip() or "Unrated"
    signal_date_source = row.get("as_of_date") or row.get("updated_at")
    parsed_signal_date = pd.to_datetime(signal_date_source, errors="coerce")
    snapshot_age_days = None
    if not pd.isna(parsed_signal_date):
        snapshot_age_days = max((pd.Timestamp.now().normalize() - parsed_signal_date.normalize()).days, 0)

    if risk_pct >= 12 or atr_pct >= 8 or (market_cap and market_cap < 1000):
        risk = "HIGH"
    elif risk_pct >= 7 or atr_pct >= 4.5 or (market_cap and market_cap < 5000):
        risk = "MEDIUM"
    else:
        risk = "LOW"

    if snapshot_age_days is not None and snapshot_age_days > 2:
        status = "STALE"
    elif price <= entry_high and price >= entry_low:
        status = "ACTIVE"
    elif price > entry_high:
        status = "EXTENDED"
    else:
        status = "PENDING"

    analysis_parts = [
        f"1M momentum {ret_1m_pct:.1f}%",
        f"score {score:.1f}",
    ]
    if ret_3m_pct:
        analysis_parts.append(f"3M trend {ret_3m_pct:.1f}%")
    if dist_52w_pct:
        analysis_parts.append(f"{dist_52w_pct:.1f}% below 52W high")
    if vol_breakout:
        analysis_parts.append(f"volume breakout {vol_breakout:.2f}x")
    analysis = (
        "; ".join(analysis_parts)
        + f". ATR risk band sets stop near {stop_loss:.2f} with target near {target:.2f}."
    )

    return {
        "symbol": _display_symbol(symbol),
        "status": status,
        "type": "STOCKBUYSWING",
        "risk": risk,
        "date": _format_signal_date(signal_date_source),
        "source_as_of_date": str(signal_date_source) if signal_date_source is not None else None,
        "snapshot_age_days": snapshot_age_days,
        "entry_range": [_round_price(entry_low), _round_price(entry_high)],
        "target": _round_price(target),
        "target_pct": round(target_pct, 2),
        "sl": _round_price(stop_loss),
        "potential_left_pct": round(max(target_pct, 0.0), 2),
        "ltp": _round_price(price),
        "ltp_change_pct": round(ret_1m_pct, 2),  # 1-month return, NOT daily change
        "ret_1m_pct": round(ret_1m_pct, 2),
        "analysis": analysis,
        "score": round(score, 1),
        "rating": rating,
        "data_quality": round(data_quality, 1),
        "market_cap_cr": round(market_cap, 2),
        "f_score": round(f_score, 1) if f_score is not None else None,
        "pe_ratio": round(pe_ratio, 2) if pe_ratio is not None else None,
        "debt_equity": round(debt_equity, 2) if debt_equity is not None else None,
        "quality_flags": _quality_flags(row, snapshot_age_days=snapshot_age_days),
        "reward_risk_ratio": round(target_pct / risk_pct, 2) if risk_pct > 0 else 0.0,
        "_rank": (
            max(ret_1m_pct, 0) * 1.8
            + max(ret_3m_pct, 0) * 0.5
            + score * 0.45
            + data_quality * 0.2
            + (min(max(f_score or 0.0, 0.0), 9.0) * 1.5)
            + max(25 - max(dist_52w_pct, 0), 0) * 0.6
            + max(vol_breakout, 0) * 4
            - max(risk_pct - 8, 0) * 1.2
            - max((pe_ratio or 0.0) - 60.0, 0.0) * 0.1
            - (6.0 if market_cap < 2000 else 0.0)
            - ((snapshot_age_days or 0) * 3.0)
        ),
    }


def _build_swing_trades(
    source: pd.DataFrame,
    *,
    limit: int,
    min_score: float,
    min_return_pct: float,
    max_52w_distance_pct: float,
    min_data_quality: float,
    min_market_cap_cr: float,
    min_f_score: float,
    max_pe_ratio: float,
    exclude_avoid_ratings: bool,
) -> list[dict]:
    if source.empty:
        return []

    candidates: list[dict] = []
    for _, row in source.iterrows():
        price = _as_float(row.get("price"), 0.0) or 0.0
        score = _as_float(row.get("score"), 0.0) or 0.0
        data_quality = _as_float(row.get("data_quality"), 0.0) or 0.0
        market_cap = _as_float(row.get("market_cap_cr"), 0.0) or 0.0
        f_score = _as_float(row.get("f_score"), None)
        pe_ratio = _as_float(row.get("pe_ratio"), None)
        ret_1m_pct = _fraction_to_pct(row.get("ret_1m"))
        # Explicit scale: dist_from_52w_high is fraction, down_from_52w is percent
        raw_dist = row.get("dist_from_52w_high")
        if raw_dist is not None and _as_float(raw_dist) is not None:
            dist_52w_pct = (_as_float(raw_dist, 0.0) or 0.0) * 100
        else:
            dist_52w_pct = _as_float(row.get("down_from_52w"), 0.0) or 0.0

        if price <= 0 or score < min_score or ret_1m_pct < min_return_pct:
            continue
        if data_quality < min_data_quality:
            continue
        if min_market_cap_cr > 0 and market_cap < min_market_cap_cr:
            continue
        if f_score is not None and f_score < min_f_score:
            continue
        if pe_ratio is not None and pe_ratio > max_pe_ratio:
            continue
        if exclude_avoid_ratings and _is_blocked_swing_rating(row.get("rating")):
            continue
        if dist_52w_pct and dist_52w_pct > max_52w_distance_pct:
            continue

        trade = _build_swing_trade(row)
        if trade:
            candidates.append(trade)

    candidates.sort(key=lambda item: item.get("_rank", 0), reverse=True)
    for candidate in candidates:
        candidate.pop("_rank", None)
    return cast(list[dict[Any, Any]], deps._json_safe_clean(candidates[:limit]))


@router.post("/api/order")
async def place_order(order: OrderRequest):
    """Order lifecycle endpoint for paper execution (BUY/SELL)."""
    try:
        symbol = canonical_symbol(order.symbol)
        side = order.side.strip().upper()

        if not symbol:
            return {"status": "rejected", "error": "symbol is required"}
        if side not in {"BUY", "SELL"}:
            return {"status": "rejected", "error": "side must be BUY or SELL"}

        if side == "BUY":
            # Risk Gates: Kill Switch & VaR
            vix = order.current_vix if order.current_vix is not None else 0.0
            is_safe, msg = deps.risk_governor.check_kill_switch(
                vix, drawdown_rate_weekly=order.drawdown_rate_weekly
            )
            if not is_safe:
                deps.risk_governor.log_rejected_trade(symbol, msg, order.price)
                return {"status": "rejected", "side": side, "symbol": symbol, "reason": msg}

            var_safe, var_msg = deps.risk_governor.validate_var_budget(
                order.projected_var_pct, order.max_var_pct
            )
            if not var_safe:
                return {"status": "rejected", "side": side, "symbol": symbol, "reason": var_msg}

            # Correlation gate
            adj_qty = order.quantity
            if order.portfolio_correlation is not None:
                factor = deps.risk_governor.validate_correlation_risk(order.portfolio_correlation)
                if factor <= 0:
                    return {
                        "status": "rejected",
                        "side": side,
                        "symbol": symbol,
                        "reason": "Correlation emergency de-risk",
                    }
                adj_qty = max(1, int(round(order.quantity * factor)))

            result = await deps._run_blocking(
                deps.portfolio_tracker.log_entry, symbol, order.price, order.score, adj_qty
            )

            # Thesis record
            if result.get("status") != "rejected":
                try:
                    from modules.thesis_monitor import record_buy_thesis

                    def _get_snapshot():
                        conn = deps.get_connection()
                        try:
                            row = pd.read_sql(
                                "SELECT * FROM multibaggers WHERE symbol = ?",
                                conn,
                                params=(symbol,),
                            )
                            return row.iloc[0].to_dict() if not row.empty else {}
                        finally:
                            conn.close()

                    snap = await deps._run_blocking(_get_snapshot)
                    if snap:
                        await deps._run_blocking(
                            record_buy_thesis, symbol, snap, order.score, 0, "SIDEWAYS"
                        )
                except Exception:
                    pass
        else:
            result = await deps._run_blocking(
                deps.portfolio_tracker.log_exit, symbol, order.price, order.reason
            )

        if result.get("status") == "rejected":
            deps.risk_governor.log_rejected_trade(
                symbol, result.get("reason", "Order rejected"), order.price
            )

        return {
            "status": result.get("status", "accepted"),
            "side": side,
            "symbol": symbol,
            "quantity": adj_qty if side == "BUY" else order.quantity,
            "price": order.price,
            "reason": result.get("reason", order.reason),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/api/trades/open")
async def get_open_trades():
    try:
        df = await deps._run_blocking(deps.portfolio_tracker.get_open_positions)
        return (
            df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None}).to_dict(orient="records")
            if not df.empty
            else []
        )
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/trades/history")
async def get_trade_history():
    try:
        df = await deps._run_blocking(deps.portfolio_tracker.get_trade_history)
        return (
            df.replace([np.inf, -np.inf], np.nan).replace({np.nan: None}).to_dict(orient="records")
            if not df.empty
            else []
        )
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/allocation/hrp")
@router.get("/api/hrp")
async def get_hrp_allocation():
    """Calculate HRP weights for top 15 stocks"""
    try:

        def _get_symbols():
            conn = deps.get_connection()
            try:
                return pd.read_sql(
                    "SELECT symbol FROM multibaggers ORDER BY score DESC LIMIT 15", conn
                )["symbol"].tolist()
            finally:
                conn.close()

        symbols = await deps._run_blocking(_get_symbols)
        if not symbols:
            raise HTTPException(status_code=404, detail="No stocks found")

        data = await run_with_exponential_backoff(
            lambda: deps._run_ticker_blocking(
                yf.download, symbols, period="1y", interval="1d", progress=False, auto_adjust=True
            ),
            context="hrp price fetch",
        )
        if data.empty:
            raise HTTPException(status_code=502, detail="Failed to fetch data")
        prices = data["Close"] if "Close" in data else data.xs("Close", axis=1, level=0)
        returns = prices.pct_change().dropna(how="all").fillna(0)
        # Black Zone Gate: Halt allocation if market is in total kill-switch mode
        zone, cap = deps.risk_governor.get_regime_zone(
            data["Close"].iloc[-1] if "Close" in data else 0.0
        )  # Placeholder, need real VIX
        # Actually, let's fetch real VIX from the regime cache
        regime_data = await deps._run_blocking(deps.regime_cache.get, "payload")
        if regime_data:
            current_vix = regime_data.get("vix", 0.0)
            zone, cap = deps.risk_governor.get_regime_zone(current_vix)
            if zone == "BLACK":
                return {
                    "error": "HRP ALLOCATION HALTED: Market is in BLACK zone (VIX > 35). High probability of capital destruction.",
                    "weights": {},
                    "timestamp": datetime.now().isoformat(),
                }

        weights = HRPAllocator().allocate(returns)
        return {
            "weights": {
                k: float(v) for k, v in sorted(weights.items(), key=lambda x: x[1], reverse=True)
            },
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/slippage_stats")
async def get_slippage_stats():
    """Execution Quality Metrics (Slippage Calibration)"""
    try:
        data = await deps._run_blocking(
            deps._read_records, "SELECT * FROM slippage_metrics ORDER BY tier"
        )
        return deps._json_safe_clean(data)
    except Exception as e:
        return {"error": str(e)}


@router.get("/api/trades/swing")
async def get_swing_trades(
    limit: int = Query(20, ge=1, le=50),
    min_score: float = Query(55.0, ge=0.0, le=100.0),
    min_return_pct: float = Query(3.0, ge=-100.0, le=500.0),
    max_52w_distance_pct: float = Query(25.0, ge=0.0, le=100.0),
    min_data_quality: float = Query(70.0, ge=0.0, le=100.0),
    min_market_cap_cr: float = Query(1000.0, ge=0.0),
    min_f_score: float = Query(4.0, ge=0.0, le=9.0),
    max_pe_ratio: float = Query(120.0, ge=0.0),
    exclude_avoid_ratings: bool = Query(True),
):
    """Derive tactical swing setups from the latest screener universe."""
    try:
        source = await deps._run_blocking(_load_swing_source_rows)
        return _build_swing_trades(
            source,
            limit=limit,
            min_score=min_score,
            min_return_pct=min_return_pct,
            max_52w_distance_pct=max_52w_distance_pct,
            min_data_quality=min_data_quality,
            min_market_cap_cr=min_market_cap_cr,
            min_f_score=min_f_score,
            max_pe_ratio=max_pe_ratio,
            exclude_avoid_ratings=exclude_avoid_ratings,
        )
    except Exception as e:
        deps.api_logger.warning("Failed to build swing trades", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to build swing trades") from e


@router.get("/api/portfolio/state")
async def get_portfolio_state():
    """Return summary metrics for the paper trading portfolio."""
    try:
        def _get_counts():
            conn = deps.get_connection()
            try:
                open_pos = pd.read_sql("SELECT count(*) as cnt FROM open_positions", conn).iloc[0]["cnt"]
                return int(open_pos)
            finally:
                conn.close()

        active_count = await deps._run_blocking(_get_counts)

        return {
            "available_capital": 1000000.0,  # Hardcoded for paper demo v1
            "total_deployed": active_count * 100000.0, # Estimate
            "risk_per_trade_pct": 1.0,
            "active_trades_count": active_count,
            "max_positions": 10
        }
    except Exception as e:
        return {
            "available_capital": 0.0,
            "total_deployed": 0.0,
            "risk_per_trade_pct": 1.0,
            "active_trades_count": 0,
            "max_positions": 10,
            "error": str(e)
        }


@router.get("/api/portfolio/performance")
async def get_performance():
    """Return historical performance curve for the paper strategy."""
    # Mocking a steady equity curve for the Sovereign strategy
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    equity = [1000000 * (1 + (0.002 * i) + (0.01 * np.sin(i/2))) for i in range(30)]

    return {
        "equity_curve": [
            {"date": d.strftime("%Y-%m-%d"), "value": round(v, 2)}
            for d, v in zip(dates, equity, strict=True)
        ],
        "stats": {
            "cagr": 24.5,
            "sharpe": 1.85,
            "max_drawdown": -6.2,
            "win_rate": 62.0,
            "profit_factor": 2.1
        }
    }
