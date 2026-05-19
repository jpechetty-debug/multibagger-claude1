"""
Scoring — Score ceiling rules, spline caps, and institutional checklist gate.

Defines the hard-cap disqualifier logic that prevents fundamentally weak
stocks from achieving high scores regardless of momentum or bonuses.
"""

from __future__ import annotations

from typing import Any

from modules.data_utils import optional_float, safe_float

from .normalization import FactorState, _Number, _StockData


def _apply_spline_cap(
    val: _Number | None,
    full_score_val: _Number,
    max_penalty_val: _Number,
    min_cap: _Number,
    name: str,
    score_ceiling: float,
    disqualifiers: list[str],
) -> float:
    val = optional_float(val)
    if val is None:
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

    profit_margin = optional_float(data.get("Profit_Margin%"))
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

    f_score_val = optional_float(data.get("F_Score"))
    if f_score_val is None:
        f_score_val = 0
    if f_score_val <= 4:
        score_ceiling = min(score_ceiling, 65 + (f_score_val * 5.9))
        disqualifiers.append(f"Quality Floor Spline (F:{f_score_val})")

    value_gap = safe_float(data.get("Value_Gap%"))
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

    cfo_pat = optional_float(data.get("CFO_PAT_Ratio"))
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

    eps_check = optional_float(data.get("EPS_Growth%"))
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


def _apply_checklist_gate(
    data: _StockData,
    state: FactorState,
    base_score: float,
    score_ceiling: float,
    disqualifiers: list[str],
) -> tuple[int, int, float, float]:
    checklist_pass = 0
    checklist_total = 12

    mcap_cr = optional_float(data.get("Market_Cap_Cr"))
    if mcap_cr is not None and mcap_cr > 1000:
        checklist_pass += 1
    if state.pe is not None and 0 < state.pe < 25:
        checklist_pass += 1
    if state.best_roe > 17:
        checklist_pass += 1
    de_val = optional_float(data.get("Debt_Equity"))
    if de_val is not None and 0 <= de_val < 1.0:
        checklist_pass += 1
    cfo_pat = optional_float(data.get("CFO_PAT_Ratio"))
    if cfo_pat is not None and cfo_pat > 1.0:
        checklist_pass += 1
    down_pct = optional_float(data.get("Down_From_52W_High%"))
    if down_pct is not None and 0 <= down_pct < 25:
        checklist_pass += 1

    sg_5y = optional_float(data.get("Sales_Growth_5Y%"))
    sg_ttm = optional_float(data.get("Sales_Growth_TTM%"))
    sg = sg_5y if sg_5y is not None else (sg_ttm if sg_ttm is not None else 0)
    if sg > 15:
        checklist_pass += 1
    eps_g = safe_float(data.get("EPS_Growth%"))
    if eps_g > 0:
        checklist_pass += 1
    if state.prom_hold > 50:
        checklist_pass += 1
    f_val_check = optional_float(data.get("F_Score"))
    if f_val_check is not None and f_val_check >= 6:
        checklist_pass += 1
    if sg > 10 and eps_g > 10:
        checklist_pass += 1
    value_gap = safe_float(data.get("Value_Gap%"))
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
