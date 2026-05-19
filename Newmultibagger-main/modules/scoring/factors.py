"""
Scoring — Factor state building, weight resolution, and ROE metrics.

Constructs the FactorState dataclass by reading raw stock data and
normalizing each factor score.
"""

from __future__ import annotations

from typing import Any

import config
from modules.data_utils import optional_float, safe_float
from modules.news_sentiment import engine as news_engine
from modules.structured_logger import logger

from .normalization import FactorState, _Number, _StockData, normalize_metric


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
    roe_5y = safe_float(data.get("Avg_ROE_5Y%"))
    roe_current = safe_float(data.get("ROE%"))
    profit_margin = safe_float(data.get("Profit_Margin%"))
    reported_roe = roe_5y if roe_5y != 0 else roe_current
    if roe_5y > 0:
        return roe_5y, reported_roe, 1.0
    if roe_current > 0:
        return roe_current, reported_roe, 0.85
    if profit_margin > 0:
        return profit_margin, reported_roe, 0.70
    return 0.0, reported_roe, 0.0


def _build_factor_state(data: _StockData, score_sentiment: float) -> FactorState:
    sales_growth_5y = safe_float(data.get("Sales_Growth_5Y%"))
    sales_growth_ttm = safe_float(data.get("Sales_Growth_TTM%"))
    sg_val = sales_growth_5y or sales_growth_ttm
    score_sales = normalize_metric(sales_growth_5y, 0, 40)

    roe_val, best_roe, roe_confidence = _calculate_roe_metrics(data)
    score_roe = normalize_metric(roe_val, 10, 30) * roe_confidence

    score_cfo = normalize_metric(safe_float(data.get("CFO_PAT_Ratio")), 0.5, 1.5)

    pe = optional_float(data.get("PE_Ratio"))
    peg = optional_float(data.get("PEG_Ratio"))
    score_pe = normalize_metric(pe, 15, 60, invert=True) if (pe is not None and pe > 0) else 0
    score_peg = normalize_metric(peg, 0.8, 2.5, invert=True) if (peg is not None and peg > 0) else 0
    if score_pe > 0 and score_peg > 0:
        score_val = (score_pe * 0.5) + (score_peg * 0.5)
    elif score_pe > 0:
        score_val = score_pe
    else:
        score_val = score_peg

    score_eps = normalize_metric(safe_float(data.get("EPS_Growth%")), 5, 30)

    f_score_val = optional_float(data.get("F_Score"))
    if f_score_val is None:
        # Phase 2.3: Missing F_Score → neutral, not penalized
        score_fscore = 50.0
    else:
        score_fscore = (f_score_val / 9.0) * 100

    stock_sector = data.get("Sector", "") or ""
    if "Bank" in stock_sector or "Financial" in stock_sector:
        score_de = 80.0
    else:
        score_de = normalize_metric(safe_float(data.get("Debt_Equity")), 0, 1.0, invert=True)

    price = safe_float(data.get("Price"))
    atr = safe_float(data.get("ATR"))
    down_from_high = safe_float(data.get("Down_From_52W_High%"))
    score_mom_tech = normalize_metric(down_from_high, 0, 40, invert=True) if price > 0 else 0

    rs_rating = optional_float(data.get("RS_Rating"))
    # Phase 2.5: Smooth sigmoid replaces coarse 25-point cliff bucketing
    score_rs = normalize_metric(rs_rating, 0.5, 1.5) if rs_rating is not None else 50.0
    score_mom_combined = (score_mom_tech * 0.5) + (score_rs * 0.5)

    # Fundamental Anchoring (Tactical Implementation)
    # Discount technical momentum if fundamentals (ROE/Sales) are poor
    fundamental_quality = (score_roe + score_sales) / 2.0
    if fundamental_quality < 40:
        anchor_discount = max(0.5, fundamental_quality / 40.0)
        score_mom_combined *= anchor_discount

    inst_hold = safe_float(data.get("Inst_Holding%"))
    prom_hold = safe_float(data.get("Promoter_Holding%"))

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
    if (
        safe_float(data.get("Sales_Growth_5Y%")) != 0
        or safe_float(data.get("Sales_Growth_TTM%")) != 0
    ):
        available.append(("sales", state.score_sales, weights["w_sales"]))
    if state.roe_val != 0:
        available.append(("roe", state.score_roe, weights["w_roe"]))
    if safe_float(data.get("CFO_PAT_Ratio")) != 0:
        available.append(("cfo", state.score_cfo, weights["w_cfo"]))
    if (state.pe is not None and state.pe > 0) or (state.peg is not None and state.peg > 0):
        available.append(("val", state.score_val, weights["w_val"]))
    if safe_float(data.get("EPS_Growth%")) != 0:
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

    base_score += safe_float(data.get("Estimate_Score_Adj"))
    return base_score, data_confidence
