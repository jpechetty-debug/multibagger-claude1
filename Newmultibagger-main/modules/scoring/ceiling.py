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
    disqualifiers: list[tuple[str, float]],
) -> float:
    val = optional_float(val)
    if val is None:
        return score_ceiling

    cap = 100.0
    if full_score_val > max_penalty_val:
        if val <= max_penalty_val:
            cap = min_cap
        elif val < full_score_val:
            denom = float(full_score_val - max_penalty_val)
            if denom == 0:
                cap = min_cap
            else:
                ratio = (full_score_val - val) / denom
                cap = 100.0 - (ratio**1.5) * (100.0 - min_cap)
    else:
        if val >= max_penalty_val:
            cap = min_cap
        elif val > full_score_val:
            denom = float(max_penalty_val - full_score_val)
            if denom == 0:
                cap = min_cap
            else:
                ratio = (val - full_score_val) / denom
                cap = 100.0 - (ratio**1.5) * (100.0 - min_cap)

    if cap < 96:
        score_ceiling = min(score_ceiling, cap)
        disqualifiers.append((f"{name} ({val:.1f})", cap))

    return score_ceiling


def _apply_score_ceiling_rules(
    data: _StockData,
    state: FactorState,
) -> tuple[float, list[tuple[str, float]]]:
    score_ceiling = 100.0
    disqualifiers: list[tuple[str, float]] = []

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
    # Only apply the ceiling when F_Score is actually present and genuinely low.
    # A missing F_Score (common for Indian mid/small-caps) is not evidence of
    # poor quality — treating None as 0 incorrectly hard-caps such stocks at 65.
    if f_score_val is not None and f_score_val <= 4:
        cap = 50 + (f_score_val * 7.5)
        score_ceiling = min(score_ceiling, cap)
        disqualifiers.append((f"Quality Floor Spline (F:{f_score_val})", cap))

    value_gap = safe_float(data.get("Value_Gap%"))
    if value_gap < 0:
        # High-growth stocks (EPS > 20%) get a relaxed floor — growth justifies premium
        eps_g_check = safe_float(data.get("EPS_Growth%"))
        ov_floor = 78 if eps_g_check > 20 else 70  # Relaxed — multibaggers often look expensive
        score_ceiling = _apply_spline_cap(
            value_gap,
            0.0,
            -70.0,
            ov_floor,
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
    # Earnings Deceleration Cap — growth is fading, past the inflection point
    pat_cagr_3y = optional_float(data.get("PAT_CAGR_3Y"))
    pat_cagr_5y = optional_float(data.get("PAT_CAGR_5Y"))
    if pat_cagr_3y is not None and pat_cagr_5y is not None and pat_cagr_5y > 10:
        decel_ratio = pat_cagr_3y / pat_cagr_5y if pat_cagr_5y > 0 else 1.0
        if decel_ratio < 0.5:
            # 3Y growth less than half of 5Y → clear deceleration
            score_ceiling = min(score_ceiling, 75.0)
            disqualifiers.append(("Earnings Deceleration", 75.0))

    # High Pledge Risk — pledged promoter shares signal financial distress
    pledge = optional_float(data.get("Pledge_Pct"))
    if pledge is not None and pledge > 25:
        pledge_cap = max(55.0, 80.0 - (pledge - 25) * 0.5)
        score_ceiling = min(score_ceiling, pledge_cap)
        disqualifiers.append((f"High Pledge Risk ({pledge:.0f}%)", pledge_cap))

    return score_ceiling, disqualifiers


# Baseline total; the optional DuPont item raises the runtime total to 13.
CHECKLIST_TOTAL = 12


def _dupont_leverage_flag(data: _StockData) -> bool | None:
    """
    PASS unless ROE looks manufactured mainly by leverage rather than by
    genuine profitability and efficient asset use.

    FAILs only when Financial Leverage (Total Assets / Equity) is high
    (>3.0x, well above the 1.5-2.5x typical of a healthy non-financial
    business) AND the underlying ROA is weak (<5%) — i.e. the core
    business is mediocre and the headline ROE is mostly a leverage effect.

    Returns None when Financial_Leverage or ROA% is missing, so the check is
    excluded from the checklist rather than treated as an unearned pass.
    """
    leverage = optional_float(data.get("Financial_Leverage"))
    roa = optional_float(data.get("ROA%"))
    if leverage is None or roa is None:
        return None
    return not (leverage > 3.0 and roa < 5.0)


def _build_checklist_items(data: _StockData, state: FactorState) -> dict[str, bool | None]:
    mcap_cr = optional_float(data.get("Market_Cap_Cr"))
    de_val = optional_float(data.get("Debt_Equity"))
    cfo_pat = optional_float(data.get("CFO_PAT_Ratio"))
    down_pct = optional_float(data.get("Down_From_52W_High%"))
    sg_5y = optional_float(data.get("Sales_Growth_5Y%"))
    sg_ttm = optional_float(data.get("Sales_Growth_TTM%"))
    if sg_ttm is not None:
        sg_ttm = max(-100.0, min(300.0, sg_ttm))
    sg = sg_5y if sg_5y is not None else (sg_ttm if sg_ttm is not None else 0)
    eps_g = safe_float(data.get("EPS_Growth%"))
    f_val_check = optional_float(data.get("F_Score"))
    value_gap = safe_float(data.get("Value_Gap%"))

    return {
        "Market Cap > 300 Cr": mcap_cr is not None and mcap_cr > 300,
        "PE < 50": state.pe is not None and 0 < state.pe < 50,
        "ROE > 17%": state.best_roe > 17,
        "Debt/Equity < 1": de_val is not None and 0 <= de_val < 1.0,
        "CFO/PAT > 1": cfo_pat is not None and cfo_pat > 1.0,
        "Within 35% of 52W High": down_pct is not None and 0 <= down_pct < 35,
        "Sales Growth > 15%": sg > 15,
        "EPS Growth > 0%": eps_g > 0,
        "Promoter > 50%": state.prom_hold > 50,
        "F-Score >= 6": f_val_check is not None and f_val_check >= 6,
        "Sales and EPS Growth > 10%": sg > 10 and eps_g > 10,
        "Value Gap > 0 or PE < 20": value_gap > 0 or (state.pe is not None and 0 < state.pe < 20),
        "ROE Not Purely Leverage-Driven": _dupont_leverage_flag(data),
    }


def _checklist_penalty_and_ceiling(
    checklist_pass: int,
    checklist_total: int = CHECKLIST_TOTAL,
) -> tuple[float, float]:
    if checklist_pass >= 9:
        checklist_penalty = (checklist_total - checklist_pass) * 0.66
        current_ceiling = 80 + (checklist_pass - 9) * (20 / 3.0)
    else:
        checklist_penalty = 2.0 + ((9 - checklist_pass) / 9.0 * 18.0)
        current_ceiling = 40 + (checklist_pass / 9.0 * 40.0)
    return checklist_penalty, current_ceiling


def build_checklist_status(data: _StockData, state: FactorState) -> dict[str, Any]:
    checks = _build_checklist_items(data, state)
    passed = sum(1 for value in checks.values() if value is True)
    total = sum(1 for value in checks.values() if value is not None)
    _, current_ceiling = _checklist_penalty_and_ceiling(passed, total)

    return {
        "items": checks,
        "passed": passed,
        "total": total,
        "grade": "A" if passed >= 7 else "B" if passed >= 5 else "C" if passed >= 3 else "D",
        "ceiling": round(current_ceiling, 1),
    }


def build_ceiling_diagnostics(data: _StockData, state: FactorState) -> list[dict[str, Any]]:
    _, disqualifiers = _apply_score_ceiling_rules(data, state)
    checklist_status = build_checklist_status(data, state)
    checklist_ceiling = float(checklist_status["ceiling"])
    if checklist_ceiling < 100:
        disqualifiers.append(
            (
                f"Institutional Quality Gate {checklist_status['passed']}/{checklist_status['total']}",
                checklist_ceiling,
            )
        )

    seen: set[tuple[str, float]] = set()
    ceilings = []
    for name, cap in sorted(disqualifiers, key=lambda item: item[1]):
        cap_value = round(float(cap), 1)
        key = (name, cap_value)
        if key in seen:
            continue
        seen.add(key)
        ceilings.append({"name": name, "cap": cap_value, "active": True})
    return ceilings


def _apply_checklist_gate(
    data: _StockData,
    state: FactorState,
    base_score: float,
    score_ceiling: float,
    disqualifiers: list[tuple[str, float]],
) -> tuple[int, int, float, float]:
    checklist_status = build_checklist_status(data, state)
    checklist_pass = int(checklist_status["passed"])
    checklist_total = int(checklist_status["total"])

    if checklist_pass >= 11:
        base_score += 5

    checklist_penalty, current_ceiling = _checklist_penalty_and_ceiling(
        checklist_pass,
        checklist_total,
    )
    base_score -= checklist_penalty
    score_ceiling = min(score_ceiling, current_ceiling)

    if checklist_pass < 9:
        disqualifiers.append((f"Institutional Quality Gate {checklist_pass}/{checklist_total}", current_ceiling))

    return checklist_pass, checklist_total, base_score, score_ceiling
