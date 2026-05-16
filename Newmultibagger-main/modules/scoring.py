from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union

import numpy as np

import config
from modules.estimates import get_estimate_data
from modules.news_sentiment import engine as news_engine
from modules.promoter_intel import calculate_promoter_score
from modules.structured_logger import logger
from research.conviction_engine import calculate_conviction_score

# Type aliases
_Number = Union[int, float]
_StockData = dict[str, Any]
_SectorMedians = dict[str, dict[str, float]]


@dataclass(frozen=True)
class FactorState:
    score_sales: float
    score_roe: float
    score_cfo: float
    score_val: float
    score_eps: float
    score_fscore: float
    score_de: float
    score_mom_combined: float
    score_sentiment: float
    sg_val: float
    roe_val: float
    best_roe: float
    pe: _Number | None
    peg: _Number | None
    price: float
    atr: float
    stock_sector: str
    prom_hold: float
    inst_hold: float


def normalize_metric(
    value: _Number | None,
    min_val: _Number,
    max_val: _Number,
    invert: bool = False,
) -> float:
    """
    Normalizes a metric to a 0-100 scale using a Sigmoid function.
    Replaces binary step cliffs with a smooth continuous gradient.
    """
    if value is None or not np.isfinite(float(value)):
        return 0.0

    mid = (min_val + max_val) / 2.0
    span = float(max_val - min_val)
    if span == 0:
        span = 1e-5

    # Scale so min_val is approx at x=-3 (4.7%) and max_val at x=+3 (95%)
    x_scaled = (value - mid) / (span / 6.0)

    # Cap exponent to avoid overflow warnings
    x_scaled = max(-100, min(100, x_scaled))

    sigmoid_val = 1.0 / (1.0 + np.exp(-x_scaled))

    if invert:
        return float((1.0 - sigmoid_val) * 100.0)
    else:
        return float(sigmoid_val * 100.0)


def calculate_sector_medians(results: list[_StockData]) -> _SectorMedians:
    """Compute median ROE, Sales Growth, PE per sector for relative scoring."""
    sector_data: dict[str, dict[str, list[float]]] = {}
    for stock in results:
        sector = stock.get("Sector", "Unknown")
        if sector == "Unknown":
            continue
        if sector not in sector_data:
            sector_data[sector] = {"roe": [], "growth": [], "pe": []}

        # Explicit None checks: 0 is a valid value that must be preserved.
        roe_5y = stock.get("Avg_ROE_5Y%")
        roe_current = stock.get("ROE%")
        roe = roe_5y if roe_5y is not None else (roe_current if roe_current is not None else None)

        growth_5y = stock.get("Sales_Growth_5Y%")
        growth_ttm = stock.get("Sales_Growth_TTM%")
        growth = growth_5y if growth_5y is not None else (growth_ttm if growth_ttm is not None else None)

        pe = stock.get("PE_Ratio")

        if roe is not None:
            sector_data[sector]["roe"].append(roe)
        if growth is not None:
            sector_data[sector]["growth"].append(growth)
        if pe is not None and pe > 0:
            sector_data[sector]["pe"].append(pe)

    medians = {}
    for sector, vals in sector_data.items():
        medians[sector] = {
            "median_roe": round(float(np.median(vals["roe"])), 1) if vals["roe"] else 15,
            "median_growth": round(float(np.median(vals["growth"])), 1) if vals["growth"] else 10,
            "median_pe": round(float(np.median(vals["pe"])), 1) if vals["pe"] else 20,
        }
    return medians


def _resolve_mode_and_weights(market_regime: str | None, sector: str = "") -> tuple[str, dict[str, float], str]:
    mode = market_regime.lower() if market_regime else "balanced"
    if mode not in config.SCORING_WEIGHTS:
        mode = "balanced"

    weights = config.SCORING_WEIGHTS[mode].copy()

    # Sector-Aware Weight Adjustments (Anthropic Pattern)
    if "Bank" in sector or "Financial" in sector:
        # For financials, Book Value and ROE are critical, Sales Growth is less relevant
        weights["w_roe"] += 0.05
        weights["w_sales"] -= 0.05
        weights["w_de"] = 0.0  # DE is not a standard metric for Banks
    elif "Tech" in sector or "Software" in sector:
        # For tech, Growth and Sentiment are prioritized
        weights["w_sales"] += 0.05
        weights["w_sentiment"] += 0.05
        weights["w_val"] -= 0.10

    # Phase 2.1: Re-normalize weights to sum to 1.0 after sector mutations
    total_weight = sum(weights.values())
    if total_weight > 0 and abs(total_weight - 1.0) > 0.001:
        weights = {k: v / total_weight for k, v in weights.items()}

    return mode, weights, mode.capitalize()


def _calculate_sentiment_factor(
    data: _StockData,
    weights: dict[str, float],
) -> tuple[float, float]:
    w_sentiment = weights.get("w_sentiment", 0.0)
    is_backtest = data.get("backtest", False) or not data.get("Symbol")
    if is_backtest:
        return 50.0, 0.0

    try:
        sentiment_data = news_engine.get_alpha_signal(data.get("Symbol", ""))
        score_sentiment = (sentiment_data["sentiment_score"] + 1.0) / 2.0 * 100.0
    except Exception as e:
        logger.warning(f"Sentiment analysis failed for {data.get('Symbol')}: {e}", exc_info=True)
        # Phase 2.4: Zero weight on failure → redistributed to other factors
        score_sentiment = 50.0
        w_sentiment = 0.0

    return score_sentiment, w_sentiment


def _calculate_roe_metrics(data: _StockData) -> tuple[float, float, float]:
    roe_5y = data.get("Avg_ROE_5Y%", 0)
    roe_current = data.get("ROE%", 0)
    profit_margin = data.get("Profit_Margin%", 0)
    reported_roe = roe_5y if roe_5y != 0 else roe_current
    if roe_5y > 0:
        return roe_5y, reported_roe, 1.0
    if roe_current > 0:
        return roe_current, reported_roe, 0.85
    if profit_margin > 0:
        return profit_margin, reported_roe, 0.70
    return 0.0, reported_roe, 0.0


def _build_factor_state(data: _StockData, score_sentiment: float) -> FactorState:
    sg_val = data.get("Sales_Growth_5Y%", 0) or data.get("Sales_Growth_TTM%", 0) or 0
    score_sales = normalize_metric(data.get("Sales_Growth_5Y%", 0), 0, 40)

    roe_val, best_roe, roe_confidence = _calculate_roe_metrics(data)
    score_roe = normalize_metric(roe_val, 10, 30) * roe_confidence

    score_cfo = normalize_metric(data.get("CFO_PAT_Ratio", 0), 0.5, 1.5)

    pe = data.get("PE_Ratio")
    peg = data.get("PEG_Ratio")
    score_pe = normalize_metric(pe, 15, 60, invert=True) if (pe is not None and pe > 0) else 0
    score_peg = normalize_metric(peg, 0.8, 2.5, invert=True) if (peg is not None and peg > 0) else 0
    if score_pe > 0 and score_peg > 0:
        score_val = (score_pe * 0.5) + (score_peg * 0.5)
    elif score_pe > 0:
        score_val = score_pe
    else:
        score_val = score_peg

    score_eps = normalize_metric(data.get("EPS_Growth%", 0), 5, 30)

    f_score_val = data.get("F_Score")
    if f_score_val is None:
        # Phase 2.3: Missing F_Score → neutral, not penalized
        score_fscore = 50.0
    else:
        score_fscore = (f_score_val / 9.0) * 100

    stock_sector = data.get("Sector", "") or ""
    if "Bank" in stock_sector or "Financial" in stock_sector:
        score_de = 80.0
    else:
        score_de = normalize_metric(data.get("Debt_Equity", 0), 0, 1.0, invert=True)

    price = data.get("Price", 0) or 0
    atr = data.get("ATR", 0) or 0
    down_from_high = data.get("Down_From_52W_High%", 0)
    score_mom_tech = normalize_metric(down_from_high, 0, 40, invert=True) if price > 0 else 0

    rs_rating = data.get("RS_Rating")
    # Phase 2.5: Smooth sigmoid replaces coarse 25-point cliff bucketing
    score_rs = normalize_metric(rs_rating, 0.5, 1.5) if rs_rating is not None else 50.0
    score_mom_combined = (score_mom_tech * 0.5) + (score_rs * 0.5)

    # Fundamental Anchoring (Tactical Implementation)
    # Discount technical momentum if fundamentals (ROE/Sales) are poor
    fundamental_quality = (score_roe + score_sales) / 2.0
    if fundamental_quality < 40:
        anchor_discount = max(0.5, fundamental_quality / 40.0)
        score_mom_combined *= anchor_discount

    inst_hold = data.get("Inst_Holding%")
    if inst_hold is None:
        inst_hold = 0
    prom_hold = data.get("Promoter_Holding%")
    if prom_hold is None:
        prom_hold = 0

    return FactorState(
        score_sales=score_sales,
        score_roe=score_roe,
        score_cfo=score_cfo,
        score_val=score_val,
        score_eps=score_eps,
        score_fscore=score_fscore,
        score_de=score_de,
        score_mom_combined=score_mom_combined,
        score_sentiment=score_sentiment,
        sg_val=sg_val,
        roe_val=roe_val,
        best_roe=best_roe,
        pe=pe,
        peg=peg,
        price=price,
        atr=atr,
        stock_sector=stock_sector,
        prom_hold=prom_hold,
        inst_hold=inst_hold,
    )


def _get_available_factors(
    data: _StockData,
    state: FactorState,
    weights: dict[str, float],
    w_sentiment: float,
) -> list[tuple[str, float, float]]:
    available = []
    if data.get("Sales_Growth_5Y%", 0) != 0 or data.get("Sales_Growth_TTM%", 0) != 0:
        available.append(("sales", state.score_sales, weights["w_sales"]))
    if state.roe_val != 0:
        available.append(("roe", state.score_roe, weights["w_roe"]))
    if data.get("CFO_PAT_Ratio", 0) != 0:
        available.append(("cfo", state.score_cfo, weights["w_cfo"]))
    if (state.pe is not None and state.pe > 0) or (state.peg is not None and state.peg > 0):
        available.append(("val", state.score_val, weights["w_val"]))
    if data.get("EPS_Growth%", 0) != 0:
        available.append(("eps", state.score_eps, weights["w_eps"]))
    available.append(("fscore", state.score_fscore, weights["w_fscore"]))
    available.append(("de", state.score_de, weights["w_de"]))
    available.append(("mom", state.score_mom_combined, weights["w_mom"]))
    available.append(("sentiment", state.score_sentiment, w_sentiment))
    return available


def _calculate_base_score(
    data: _StockData,
    state: FactorState,
    weights: dict[str, float],
    w_sentiment: float,
) -> tuple[float, float]:
    available = _get_available_factors(data, state, weights, w_sentiment)
    data_confidence = round((len(available) / 9) * 100, 1)

    if available:
        total_available_weight = sum(weight for _, _, weight in available)
        scale = 1.0 / total_available_weight if total_available_weight > 0 else 1.0
        base_score = sum(score * weight * scale for _, score, weight in available)
    else:
        base_score = 0.0

    factor_count = len(available)
    if factor_count < 6:
        data_multiplier = max(0.1, min(1.0, (factor_count / 6.0) ** 1.5))
        base_score *= data_multiplier

    base_score += data.get("Estimate_Score_Adj", 0)
    return base_score, data_confidence


def _apply_sector_relative_adjustment(
    base_score: float,
    state: FactorState,
    sector_medians: _SectorMedians | None,
) -> float:
    if not sector_medians or state.stock_sector not in sector_medians:
        return base_score

    sm = sector_medians[state.stock_sector]
    sector_rel_bonus = 0
    if state.best_roe > sm["median_roe"] * 1.2:
        sector_rel_bonus += 3
    elif state.best_roe > 0 and state.best_roe < sm["median_roe"] * 0.5:
        sector_rel_bonus -= 5

    if state.sg_val > sm["median_growth"] * 1.2:
        sector_rel_bonus += 3
    elif state.sg_val > 0 and state.sg_val < sm["median_growth"] * 0.5:
        sector_rel_bonus -= 5

    sector_rel_bonus = max(-10, min(6, sector_rel_bonus))
    return base_score + sector_rel_bonus


def _calculate_bonus_total(data: _StockData, state: FactorState, sector_boost: _Number) -> float:
    total_bonus: float = 0.0
    inflection_score = data.get("Earnings_Inflection_Score")
    if inflection_score is None:
        inflection_score = 0
    if inflection_score >= 4:
        total_bonus += 8
    elif inflection_score >= 3:
        total_bonus += 5
    elif inflection_score >= 2:
        total_bonus += 3
    elif data.get("Earnings_Accel"):
        total_bonus += 2

    total_bonus += sector_boost

    value_gap = data.get("Value_Gap%", 0)
    if value_gap > 50:
        total_bonus += 10
    elif value_gap > 20:
        total_bonus += 5

    f_score_check = data.get("F_Score")
    if f_score_check is not None and f_score_check >= 8:
        total_bonus += 5

    if data.get("Technical_Signal") == "Bullish":
        total_bonus += 5

    rating = str(data.get("Analyst_Rating") or "").lower()
    upside = data.get("Analyst_Upside%")
    if upside is None:
        upside = 0
    if "strong buy" in rating:
        total_bonus += 5
    elif "buy" in rating:
        total_bonus += 2
    if upside > 20:
        total_bonus += 5

    if state.inst_hold > 20:
        total_bonus += 5
    elif state.inst_hold > 10:
        total_bonus += 2
    if state.prom_hold > 60:
        total_bonus += 3

    if state.price > 0:
        atr_pct = state.atr / state.price
        if atr_pct < 0.03:
            total_bonus += 2

    if state.pe is not None and 0 < state.pe < 12 and data.get("Avg_ROE_5Y%", 0) > 25:
        total_bonus += 7
    if state.pe is not None and 0 < state.pe < 7 and data.get("Avg_ROE_5Y%", 0) > 15:
        total_bonus += 7

    if (
        "Utility" in state.stock_sector
        or "Energy" in state.stock_sector
        or "Power" in state.stock_sector
    ):
        de_check = data.get("Debt_Equity")
        fs_check = data.get("F_Score")
        if (de_check is not None and de_check > 1.0) and (fs_check is not None and fs_check >= 6):
            total_bonus += 5

    return min(total_bonus, 15)


def _apply_penalty_rules(
    base_score: float,
    data: _StockData,
    state: FactorState,
    factor_audit: list[dict[str, Any]],
) -> float:
    total_penalty = 0

    if state.price > 0:
        atr_pct = state.atr / state.price
        if atr_pct > 0.07:
            total_penalty += 2
            factor_audit.append({"name": "High Volatility", "value": -2})
        if atr_pct > 0.10:
            total_penalty += 5
            factor_audit.append({"name": "Extreme Volatility", "value": -5})

    sales_5y = data.get("Sales_Growth_5Y%", 0)
    sales_ttm = data.get("Sales_Growth_TTM%", 0)
    if sales_5y < 0 and sales_ttm < 0:
        total_penalty += 5
        factor_audit.append({"name": "Declining Revenue (Long & Short)", "value": -5})
    elif sales_5y < 0 or sales_ttm < 0:
        total_penalty += 3
        factor_audit.append({"name": "Declining Revenue (Partial)", "value": -3})

    if state.pe is not None and state.pe > 80:
        total_penalty += 5
        factor_audit.append({"name": "Extreme Overvaluation", "value": -5})
    elif state.pe is not None and state.pe > 60:
        total_penalty += 3
        factor_audit.append({"name": "High Overvaluation", "value": -3})

    if state.prom_hold > 0 and state.prom_hold < 20:
        total_penalty += 5
        factor_audit.append({"name": "Low Promoter Holding (<20%)", "value": -5})
    elif state.prom_hold > 0 and state.prom_hold < 30:
        total_penalty += 2
        factor_audit.append({"name": "Low Promoter Holding (<30%)", "value": -2})

    return base_score - total_penalty


def _apply_checklist_gate(
    data: _StockData,
    state: FactorState,
    base_score: float,
    score_ceiling: float,
    disqualifiers: list[str],
) -> tuple[int, int, float, float]:
    checklist_pass = 0
    checklist_total = 12

    mcap_cr = data.get("Market_Cap_Cr")
    if mcap_cr is not None and mcap_cr > 1000:
        checklist_pass += 1
    if state.pe is not None and 0 < state.pe < 25:
        checklist_pass += 1
    if state.best_roe > 17:
        checklist_pass += 1
    de_val = data.get("Debt_Equity")
    if de_val is not None and 0 <= de_val < 1.0:
        checklist_pass += 1
    cfo_pat = data.get("CFO_PAT_Ratio")
    if cfo_pat is not None and cfo_pat > 1.0:
        checklist_pass += 1
    down_pct = data.get("Down_From_52W_High%")
    if down_pct is not None and 0 <= down_pct < 25:
        checklist_pass += 1

    sg_5y = data.get("Sales_Growth_5Y%")
    sg_ttm = data.get("Sales_Growth_TTM%")
    sg = sg_5y if sg_5y is not None else (sg_ttm if sg_ttm is not None else 0)
    if sg > 15:
        checklist_pass += 1
    eps_g = data.get("EPS_Growth%")
    eps_g = eps_g if eps_g is not None else 0
    if eps_g > 0:
        checklist_pass += 1
    if state.prom_hold > 50:
        checklist_pass += 1
    f_val_check = data.get("F_Score")
    if f_val_check is not None and f_val_check >= 6:
        checklist_pass += 1
    if sg > 10 and eps_g > 10:
        checklist_pass += 1
    value_gap = data.get("Value_Gap%", 0)
    if value_gap > 0 or (state.pe is not None and 0 < state.pe < 20):
        checklist_pass += 1

    if checklist_pass >= 11:
        base_score += 5

    if checklist_pass >= 9:
        checklist_penalty = (12 - checklist_pass) * 0.66
        current_ceiling = 80 + (checklist_pass - 9) * (20 / 3.0)
    else:
        checklist_penalty = 2.0 + ((9 - checklist_pass) / 9.0 * 18.0)
        current_ceiling = 40 + (checklist_pass / 9.0 * 40.0)

    base_score -= checklist_penalty
    score_ceiling = min(score_ceiling, current_ceiling)

    if checklist_pass < 9:
        disqualifiers.append(f"Institutional Quality Gate {checklist_pass}/{checklist_total}")

    return checklist_pass, checklist_total, base_score, score_ceiling


def _build_conviction_input(data: _StockData) -> _StockData:
    return {
        "symbol": data.get("Symbol", ""),
        "sales_growth": data.get("Sales_Growth_5Y%", 0),
        "profit_growth": data.get("EPS_Growth%", 0),
        "roce": data.get("Avg_ROE_5Y%", 0),
        "debt_to_equity": data.get("Debt_Equity", 0),
        "promoter_holding": data.get("Promoter_Holding%", 0),
        "pledge": 0,
    }


def _apply_spline_cap(
    val: _Number | None,
    full_score_val: _Number,
    max_penalty_val: _Number,
    min_cap: _Number,
    name: str,
    score_ceiling: float,
    disqualifiers: list[str],
) -> float:
    if val is None or not np.isfinite(val):
        return score_ceiling

    cap = 100.0
    if full_score_val > max_penalty_val:
        if val <= max_penalty_val:
            cap = min_cap
        elif val < full_score_val:
            ratio = (full_score_val - val) / float(full_score_val - max_penalty_val)
            cap = 100.0 - (ratio**1.5) * (100.0 - min_cap)
    else:
        if val >= max_penalty_val:
            cap = min_cap
        elif val > full_score_val:
            ratio = (val - full_score_val) / float(max_penalty_val - full_score_val)
            cap = 100.0 - (ratio**1.5) * (100.0 - min_cap)

    if cap < 96:
        score_ceiling = min(score_ceiling, cap)
        disqualifiers.append(f"{name} ({val:.1f})")

    return score_ceiling


def _apply_score_ceiling_rules(
    data: _StockData,
    state: FactorState,
) -> tuple[float, list[str]]:
    score_ceiling = 100.0
    disqualifiers: list[str] = []

    score_ceiling = _apply_spline_cap(
        state.best_roe,
        15.0,
        0.0,
        60,
        "ROE Decay Spline",
        score_ceiling,
        disqualifiers,
    )
    if state.best_roe < 0:
        score_ceiling = _apply_spline_cap(
            state.best_roe,
            0.0,
            -15.0,
            40,
            "Value Destruction Spline",
            score_ceiling,
            disqualifiers,
        )

    if state.sg_val is not None:
        score_ceiling = _apply_spline_cap(
            state.sg_val,
            10.0,
            -5.0,
            60,
            "Growth Decay Spline",
            score_ceiling,
            disqualifiers,
        )
        if state.sg_val < -5:
            score_ceiling = _apply_spline_cap(
                state.sg_val,
                -5.0,
                -25.0,
                40,
                "Declining Revenue Spline",
                score_ceiling,
                disqualifiers,
            )

    if state.best_roe > 100:
        score_ceiling = _apply_spline_cap(
            state.best_roe,
            100.0,
            250.0,
            45,
            "Anomalous ROE Risk",
            score_ceiling,
            disqualifiers,
        )

    profit_margin = data.get("Profit_Margin%", 0)
    if profit_margin is not None:
        score_ceiling = _apply_spline_cap(
            profit_margin,
            10.0,
            -5.0,
            60,
            "Margin Decay Spline",
            score_ceiling,
            disqualifiers,
        )

    f_score_val = data.get("F_Score")
    if f_score_val is None:
        f_score_val = 0
    if f_score_val <= 4:
        score_ceiling = min(score_ceiling, 65 + (f_score_val * 5.9))
        disqualifiers.append(f"Quality Floor Spline (F:{f_score_val})")

    value_gap = data.get("Value_Gap%", 0)
    if value_gap < 0:
        score_ceiling = _apply_spline_cap(
            value_gap,
            0.0,
            -70.0,
            65,
            "Overvaluation Spline",
            score_ceiling,
            disqualifiers,
        )

    cfo_pat = data.get("CFO_PAT_Ratio", 0)
    if cfo_pat is not None:
        score_ceiling = _apply_spline_cap(
            cfo_pat,
            0.8,
            0.0,
            60,
            "Cash Quality Spline",
            score_ceiling,
            disqualifiers,
        )

    if state.prom_hold > 0 and state.inst_hold < 10:
        score_ceiling = _apply_spline_cap(
            state.prom_hold,
            30.0,
            10.0,
            65,
            "Anchor Investor Spline",
            score_ceiling,
            disqualifiers,
        )

    eps_check = data.get("EPS_Growth%", 0)
    if eps_check is not None:
        score_ceiling = _apply_spline_cap(
            eps_check,
            10.0,
            -10.0,
            65,
            "EPS Decay Spline",
            score_ceiling,
            disqualifiers,
        )

    factor_scores = [
        state.score_sales,
        state.score_roe,
        state.score_cfo,
        state.score_val,
        state.score_eps,
        state.score_fscore,
        state.score_de,
        state.score_mom_combined,
    ]
    avg_quality = sum(factor_scores) / len(factor_scores)
    score_ceiling = _apply_spline_cap(
        avg_quality,
        50.0,
        30.0,
        55,
        "Lopsided Profile Spline",
        score_ceiling,
        disqualifiers,
    )

    cyclical_sectors = {"Energy", "Basic Materials", "Utilities"}
    if (
        state.stock_sector in cyclical_sectors
        and state.best_roe > 0
        and state.pe is not None
        and state.pe > 0
    ):
        cycle_risk = state.best_roe / state.pe
        score_ceiling = _apply_spline_cap(
            cycle_risk,
            2.0,
            5.0,
            65,
            "Cyclical Peak Spline",
            score_ceiling,
            disqualifiers,
        )

    return score_ceiling, disqualifiers


def _apply_optional_intel_adjustments(
    data: _StockData,
    factor_audit: list[dict[str, Any]],
    score_ceiling: float,
    disqualifiers: list[str],
) -> tuple[float, float, float, list[str]]:
    total_bonus = 0.0
    total_penalty = 0.0
    symbol = data.get("Symbol", "")

    try:
        promoter_result = calculate_promoter_score(symbol) or {}
        if promoter_result.get("is_disqualified"):
            score_ceiling = min(score_ceiling, 60)
            disqualifiers.append("D15: Heavy Insider Sell-Off")
            factor_audit.append({"name": "D15: Heavy Insider Sell-Off", "value": -40})

        promoter_adjustment = promoter_result.get("score_adjustment", 0)
        if promoter_adjustment > 0:
            total_bonus += promoter_adjustment
            factor_audit.append({"name": "Promoter Buying Boost", "value": promoter_adjustment})
        elif promoter_adjustment < 0:
            total_penalty += abs(promoter_adjustment)
            factor_audit.append({"name": "Promoter Selling Penalty", "value": promoter_adjustment})
    except Exception as e:
        logger.warning(f"Promoter score adjustment failed for {symbol}: {e}", exc_info=True)

    try:
        estimate_result = get_estimate_data(symbol) or {}
        estimate_momentum = estimate_result.get("momentum", {})
        if estimate_momentum.get("is_disqualified"):
            score_ceiling = min(score_ceiling, 55)
            disqualifiers.append("D16: Estimate Collapse (3Q consecutive downgrades)")
            factor_audit.append({"name": "D16: Estimate Collapse", "value": -45})

        estimate_cap = estimate_momentum.get("score_cap")
        if estimate_cap is not None:
            score_ceiling = min(score_ceiling, estimate_cap)
            disqualifiers.append(f"Earnings Miss Streak (cap {estimate_cap})")
            factor_audit.append({"name": "Earnings Miss Streak", "value": -(100 - estimate_cap)})

        estimate_adjustment = estimate_momentum.get("score_adjustment", 0)
        if estimate_adjustment > 0:
            total_bonus += estimate_adjustment
            factor_audit.append({"name": "Estimate Momentum Bonus", "value": estimate_adjustment})
        elif estimate_adjustment < 0:
            total_penalty += abs(estimate_adjustment)
            factor_audit.append(
                {"name": "Estimate Downgrade Penalty", "value": estimate_adjustment}
            )
    except Exception as e:
        logger.warning(f"Estimate data adjustment failed for {symbol}: {e}", exc_info=True)

    # Cap extra bonuses to 10 points to prevent stacking (Issue 6)
    return min(total_bonus, 10.0), total_penalty, score_ceiling, disqualifiers


def _calculate_tiebreak_epsilon(symbol: str) -> float:
    import hashlib

    sym_hash = int(hashlib.md5(symbol.encode(), usedforsecurity=False).hexdigest(), 16) % 1000
    return sym_hash / 100000.0


def _build_factor_breakdown(
    state: FactorState,
    weights: dict[str, float],
    w_sentiment: float,
    conviction: dict[str, Any],
    sector_boost: _Number,
) -> dict[str, float]:
    return {
        "Fundamentals": round(
            (
                state.score_sales * weights["w_sales"]
                + state.score_roe * weights["w_roe"]
                + state.score_cfo * weights["w_cfo"]
                + state.score_eps * weights["w_eps"]
            ),
            1,
        ),
        "Value": round(state.score_val * weights["w_val"], 1),
        "Risk": round(
            (state.score_fscore * weights["w_fscore"] + state.score_de * weights["w_de"]),
            1,
        ),
        "Momentum": round(state.score_mom_combined * weights["w_mom"], 1),
        "News_Sentiment": round(state.score_sentiment * w_sentiment, 1),
        "Smart_Money": 10 if conviction["institutional_interest"] else 0,
        "Sector": sector_boost,
    }


def calculate_institutional_score(
    data: _StockData,
    sector_boost: _Number = 0,
    market_regime: str = "Neutral",
    sector_medians: _SectorMedians | None = None,
) -> dict[str, Any]:
    """
    Calculates a 'Composite Institutional Score' out of 100.
    Phase 23: Dynamic Factor Weights based on Market Regime.
    - [x] **Phase 1: Sentiment Engine Core**
        - [x] Create `modules/news_sentiment.py` for headline analysis.
        - [x] Implement local VADER/HuggingFace fallback for sentiment scoring.
    - [x] **Phase 2: Scoring Model Integration**
        - [x] Add `w_sentiment` to `SCORING_WEIGHTS` in `config.py`.
        - [x] Integrate `NewsSentimentEngine` into `modules/scoring.py`.
        - [x] Update `total_score` calculation to include the 9th factor.
    """
    _, weights, scoring_strategy = _resolve_mode_and_weights(market_regime, sector=data.get("Sector", ""))
    score_sentiment, w_sentiment = _calculate_sentiment_factor(data, weights)
    state = _build_factor_state(data, score_sentiment)
    base_score, data_confidence = _calculate_base_score(data, state, weights, w_sentiment)
    base_score = _apply_sector_relative_adjustment(base_score, state, sector_medians)

    factor_audit: list[dict[str, Any]] = []
    # 2. Global Bonus Collection (Issue 6)
    bonus_accumulated = _calculate_bonus_total(data, state, sector_boost)

    conviction = calculate_conviction_score(_build_conviction_input(data))
    if conviction["institutional_interest"]:
        bonus_accumulated += 10

    cagr_consistency = data.get("CAGR_Consistency", "UNKNOWN")
    if cagr_consistency == "HIGH":
        bonus_accumulated += 5
        factor_audit.append({"name": "CAGR Consistency (HIGH)", "value": 5})
    elif cagr_consistency == "MEDIUM":
        bonus_accumulated += 2
        factor_audit.append({"name": "CAGR Consistency (MEDIUM)", "value": 2})

    score_ceiling, disqualifiers = _apply_score_ceiling_rules(data, state)
    extra_bonus, extra_penalty, score_ceiling, disqualifiers = _apply_optional_intel_adjustments(
        data,
        factor_audit,
        score_ceiling,
        disqualifiers,
    )
    bonus_accumulated += extra_bonus

    # Phase 2.2: Proportional bonus cap — max 15 points or 20% of base_score,
    # whichever is smaller. Prevents non-fundamental inflation.
    max_bonus = min(15.0, base_score * 0.20)
    final_bonus = min(bonus_accumulated, max_bonus)
    base_score += final_bonus

    # 3. Apply Penalties (Not capped by bonus limit)
    base_score = _apply_penalty_rules(base_score, data, state, factor_audit)
    if cagr_consistency == "LOW":
        base_score -= 3
        factor_audit.append({"name": "CAGR Consistency (LOW)", "value": -3})
    base_score -= extra_penalty

    checklist_pass, checklist_total, base_score, score_ceiling = _apply_checklist_gate(
        data,
        state,
        base_score,
        score_ceiling,
        disqualifiers,
    )

    base_score += _calculate_tiebreak_epsilon(data.get("Symbol", ""))
    final_score = min(base_score, score_ceiling)

    for disqualifier in disqualifiers:
        factor_audit.append({"name": disqualifier, "value": round(score_ceiling - 100, 1)})

    raw_score = round(max(0, min(base_score, 100.0)), 1)

    # Cap institutional conviction score so it doesn't bypass the fundamental score ceiling
    capped_conviction_score = min(conviction["conviction_score"], score_ceiling)

    return {
        "total_score": round(max(0, min(final_score, 100.0)), 5),
        "raw_score": raw_score,
        "checklist_score": f"{checklist_pass}/{checklist_total}",
        "data_confidence": data_confidence,
        "conviction_score": capped_conviction_score,
        "conviction_boost": conviction["conviction_boost"],
        "institutional_interest": conviction["institutional_interest"],
        "super_investors": ", ".join(conviction["investors"]),
        "scoring_strategy": scoring_strategy,
        "factor_penalties": factor_audit,
        "factor_breakdown": _build_factor_breakdown(
            state,
            weights,
            w_sentiment,
            conviction,
            sector_boost,
        ),
    }
