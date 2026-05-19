"""
Scoring — Bonus, penalty, and intelligence-driven score adjustments.

Includes sector-relative bonuses, categorical penalties, promoter intel,
and analyst estimate adjustments.
"""

from __future__ import annotations

from typing import Any

from modules.data_utils import optional_float, safe_float
from modules.estimates import get_estimate_data
from modules.promoter_intel import calculate_promoter_score
from modules.structured_logger import logger

from .normalization import FactorState, _Number, _SectorMedians, _StockData


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
    inflection_score = safe_float(data.get("Earnings_Inflection_Score"))
    if inflection_score >= 4:
        total_bonus += 8
    elif inflection_score >= 3:
        total_bonus += 5
    elif inflection_score >= 2:
        total_bonus += 3
    elif data.get("Earnings_Accel"):
        total_bonus += 2

    total_bonus += sector_boost

    value_gap = safe_float(data.get("Value_Gap%"))
    if value_gap > 50:
        total_bonus += 10
    elif value_gap > 20:
        total_bonus += 5

    f_score_check = optional_float(data.get("F_Score"))
    if f_score_check is not None and f_score_check >= 8:
        total_bonus += 5

    if data.get("Technical_Signal") == "Bullish":
        total_bonus += 5

    rating = str(data.get("Analyst_Rating") or "").lower()
    upside = safe_float(data.get("Analyst_Upside%"))
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

    avg_roe_5y = safe_float(data.get("Avg_ROE_5Y%"))
    if state.pe is not None and 0 < state.pe < 12 and avg_roe_5y > 25:
        total_bonus += 7
    if state.pe is not None and 0 < state.pe < 7 and avg_roe_5y > 15:
        total_bonus += 7

    if (
        "Utility" in state.stock_sector
        or "Energy" in state.stock_sector
        or "Power" in state.stock_sector
    ):
        de_check = optional_float(data.get("Debt_Equity"))
        fs_check = optional_float(data.get("F_Score"))
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

    sales_5y = safe_float(data.get("Sales_Growth_5Y%"))
    sales_ttm = safe_float(data.get("Sales_Growth_TTM%"))
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
