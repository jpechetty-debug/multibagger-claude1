"""
Scoring — Bonus, penalty, and intelligence-driven score adjustments.

Phase 1 rebalance:
- Merged overlapping bonuses (ROCE/ROE, mcap/growth combos)
- Reduced bonus cap from 18 → 12 to prevent mediocre stock inflation
- Made bonuses multiplicative-aware (quality tiers)
- Penalties are proportional and additive
- Removed absolute mcap bias — small cap advantage is via tiered filters, not bonus inflation
"""

from __future__ import annotations

from typing import Any

from modules.data_utils import optional_float, safe_float
from modules.estimates import get_estimate_data
from modules.promoter_intel import calculate_promoter_score
from core.observability.logger import logger

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
    """
    Rebalanced bonus system — 3 quality tiers with capped stacking.

    Tier A (High-conviction signals): max 5 pts each, max 2 signals = 10 pts
    Tier B (Supporting signals): max 3 pts each, max 2 signals = 6 pts
    Tier C (Confirming signals): max 2 pts each

    Total bonus hard-capped at 12 (was effectively ~50 uncapped).
    """
    tier_a_bonus: float = 0.0  # High-conviction: earnings inflection, value gap
    tier_b_bonus: float = 0.0  # Supporting: quality, ownership
    tier_c_bonus: float = 0.0  # Confirming: technical, low vol, sector

    # ── TIER A: Earnings & Valuation (max 10 pts) ───────────────────────
    # Earnings inflection — the single most predictive multibagger signal
    inflection_score = safe_float(data.get("Earnings_Inflection_Score"))
    if inflection_score >= 4:
        tier_a_bonus += 5
    elif inflection_score >= 3:
        tier_a_bonus += 3
    elif inflection_score >= 2:
        tier_a_bonus += 2
    elif inflection_score >= 1:
        tier_a_bonus += 1
    elif safe_float(data.get("Earnings_Accel")):
        tier_a_bonus += 1

    # Value gap — margin of safety
    value_gap = safe_float(data.get("Value_Gap%"))
    if value_gap > 50:
        tier_a_bonus += 5
    elif value_gap > 20:
        tier_a_bonus += 3

    tier_a_bonus = min(10, tier_a_bonus)

    # ── TIER B: Quality & Ownership (max 6 pts) ────────────────────────
    # Compounding quality — ROCE+ROE combined (was separate, causing double-count)
    roce = optional_float(data.get("ROCE%"))
    if roce is not None and state.best_roe > 0:
        avg_quality = (roce + state.best_roe) / 2
        if avg_quality > 30:
            tier_b_bonus += 3  # Exceptional (was 5+5=10 for ROCE>30 AND ROE>17)
        elif avg_quality > 20:
            tier_b_bonus += 2
    elif state.best_roe > 25:
        tier_b_bonus += 2

    # F-Score — quality floor (only really high scores rewarded)
    f_score_check = optional_float(data.get("F_Score"))
    if f_score_check is not None and f_score_check >= 8:
        tier_b_bonus += 3

    # Consistent compounder — PAT CAGR both 3Y and 5Y strong
    # (Merged: was separate ROCE bonus + PAT bonus causing overlap)
    pat_cagr_3y = optional_float(data.get("PAT_CAGR_3Y"))
    pat_cagr_5y = optional_float(data.get("PAT_CAGR_5Y"))
    if pat_cagr_3y is not None and pat_cagr_5y is not None:
        if pat_cagr_3y > 20 and pat_cagr_5y > 20:
            tier_b_bonus += 3
        elif pat_cagr_3y > 15 and pat_cagr_5y > 15:
            tier_b_bonus += 1

    tier_b_bonus = min(6, tier_b_bonus)

    # ── TIER C: Confirming signals (max 4 pts) ─────────────────────────
    tier_c_bonus += sector_boost  # Sector outperformance

    # Ownership alignment — ONE bonus for combined ownership strength
    # (Was: inst>20 +5, prom>60 +3, creating 8 pts for a common combo)
    if state.inst_hold > 20 and state.prom_hold > 50:
        tier_c_bonus += 2  # Strong alignment
    elif state.inst_hold > 15 or state.prom_hold > 55:
        tier_c_bonus += 1

    # Low volatility confirmation
    if state.price > 0:
        atr_pct = abs(state.atr) / state.price
        if atr_pct < 0.03:
            tier_c_bonus += 1

    # Technical confirmation
    if data.get("Technical_Signal") == "Bullish":
        tier_c_bonus += 1

    # Deep value combo — PE < 10 with ROE > 25 (rare, high-conviction)
    if state.pe is not None and 0 < state.pe < 10 and state.best_roe > 25:
        tier_c_bonus += 2

    # Volume breakout — institutional accumulation
    vol_breakout = optional_float(data.get("Vol_Breakout"))
    if vol_breakout is not None and vol_breakout > 2.0:
        tier_c_bonus += 1

    tier_c_bonus = min(4, tier_c_bonus)

    # Analyst sentiment — separate small bonus
    analyst_bonus = 0.0
    rating = str(data.get("Analyst_Rating") or "").lower()
    upside = safe_float(data.get("Analyst_Upside%"))
    if "strong buy" in rating:
        analyst_bonus += 2
    elif "buy" in rating:
        analyst_bonus += 1
    if upside > 20:
        analyst_bonus += 1
    analyst_bonus = min(3, analyst_bonus)

    # ── Margin expansion signal (kept, but capped) ─────────────────────
    margin_bonus = 0.0
    opm = optional_float(data.get("Operating_Margin%"))
    opm_5y = optional_float(data.get("Avg_OPM_5Y%"))
    if opm is not None and opm_5y is not None and opm_5y > 0:
        margin_expansion = opm - opm_5y
        if margin_expansion > 5:
            margin_bonus += 2
        elif margin_expansion > 2:
            margin_bonus += 1

    # ── TOTAL: Hard cap at 12 ──────────────────────────────────────────
    raw_total = tier_a_bonus + tier_b_bonus + tier_c_bonus + analyst_bonus + margin_bonus

    # Utility/Energy sector D/E exemption (carried forward)
    if (
        "Utility" in state.stock_sector
        or "Energy" in state.stock_sector
        or "Power" in state.stock_sector
    ):
        de_check = optional_float(data.get("Debt_Equity"))
        fs_check = optional_float(data.get("F_Score"))
        if (de_check is not None and de_check > 1.0) and (fs_check is not None and fs_check >= 6):
            raw_total += 2

    return min(12.0, raw_total)


def _apply_penalty_rules(
    base_score: float,
    data: _StockData,
    state: FactorState,
    factor_audit: list[dict[str, Any]],
) -> float:
    total_penalty = 0

    if state.price > 0:
        atr_pct = abs(state.atr) / state.price
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
    disqualifiers: list[tuple[str, float]],
) -> tuple[float, float, float, list[tuple[str, float]]]:
    total_bonus = 0.0
    total_penalty = 0.0
    symbol = data.get("Symbol", "")

    try:
        promoter_result = calculate_promoter_score(symbol) or {}
        if promoter_result.get("is_disqualified"):
            score_ceiling = min(score_ceiling, 60)
            disqualifiers.append(("D15: Heavy Insider Sell-Off", 60))
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
            disqualifiers.append(("D16: Estimate Collapse (3Q consecutive downgrades)", 55))
            factor_audit.append({"name": "D16: Estimate Collapse", "value": -45})

        estimate_cap = estimate_momentum.get("score_cap")
        if estimate_cap is not None:
            score_ceiling = min(score_ceiling, estimate_cap)
            disqualifiers.append((f"Earnings Miss Streak (cap {estimate_cap})", estimate_cap))
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

    # Cap intel bonuses to 8 points (was 10 — tightened to match new bonus budget)
    return min(total_bonus, 8.0), total_penalty, score_ceiling, disqualifiers
