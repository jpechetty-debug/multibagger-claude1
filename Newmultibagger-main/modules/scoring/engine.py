"""
Scoring — Institutional score orchestrator.

This is the top-level engine that composes factor computation, adjustments,
ceiling rules, and conviction scoring into the final composite score.
"""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from config import MAX_FUNDAMENTAL_AGE_DAYS, STALE_DATA_WARNING_DAYS

from modules.data_utils import safe_float
from modules.data_layer.dq_gates import validate_record
from modules.pit_auditor import enforce_pit_gate
from research.conviction_engine import calculate_conviction_score

from .adjustments import (
    _apply_optional_intel_adjustments,
    _apply_penalty_rules,
    _apply_sector_relative_adjustment,
    _calculate_bonus_total,
)
from .ceiling import _apply_checklist_gate, _apply_score_ceiling_rules
from .factors import (
    _build_factor_state,
    _calculate_base_score,
    _calculate_sentiment_factor,
    _resolve_mode_and_weights,
)
from .normalization import FactorState, _Number, _SectorMedians, _StockData


def _build_conviction_input(data: _StockData) -> _StockData:
    return {
        "symbol": data.get("Symbol", ""),
        "sales_growth": safe_float(data.get("Sales_Growth_5Y%")),
        "profit_growth": safe_float(data.get("EPS_Growth%")),
        "roce": safe_float(data.get("Avg_ROE_5Y%")),
        "debt_to_equity": safe_float(data.get("Debt_Equity")),
        "promoter_holding": safe_float(data.get("Promoter_Holding%")),
        "pledge": 0,
    }


def _calculate_tiebreak_epsilon(symbol: str) -> float:
    sym_hash = int(hashlib.md5(symbol.encode(), usedforsecurity=False).hexdigest(), 16) % 1000
    return sym_hash / 100000.0


def _stale_data_result(data: _StockData, age_days: int) -> dict[str, Any]:
    symbol = data.get("Symbol") or data.get("symbol") or "UNKNOWN"
    return {
        "total_score": 0.0,
        "raw_score": 0.0,
        "checklist_score": "0/12",
        "data_confidence": 0.0,
        "data_quality_flags": ["stale_data"],
        "conviction_score": 0.0,
        "conviction_boost": 0.0,
        "institutional_interest": False,
        "super_investors": "",
        "scoring_strategy": "STALE_DATA",
        "factor_penalties": [
            {
                "name": "STALE_DATA",
                "value": -100,
                "age_days": age_days,
                "max_age_days": MAX_FUNDAMENTAL_AGE_DAYS,
            }
        ],
        "factor_breakdown": {
            "Fundamentals": 0.0,
            "Value": 0.0,
            "Risk": 0.0,
            "Momentum": 0.0,
            "News_Sentiment": 0.0,
            "Smart_Money": 0.0,
            "Sector": 0.0,
        },
        "signal": "STALE_DATA",
        "status": "STALE_DATA",
        "error_code": "STALE_DATA",
        "warning": (
            f"Data for {symbol} is {age_days} days old; "
            f"max allowed is {MAX_FUNDAMENTAL_AGE_DAYS} days."
        ),
        "stale_data": {
            "symbol": symbol,
            "age_days": age_days,
            "max_age_days": MAX_FUNDAMENTAL_AGE_DAYS,
        },
    }


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
    # ── Extract shared date fields once ──
    as_of = data.get("As_Of_Date")
    quarter_end = data.get("Quarter_End")

    # ── PIT hard gate: block scoring if data is too fresh (SEBI 45-day lag) ──
    if quarter_end and as_of:
        enforce_pit_gate(as_of, quarter_end, symbol=data.get("Symbol", "UNKNOWN"))

    # ── Data freshness soft gate: penalise stale data instead of blocking ──
    data_quality_flags: list[str] = []
    _staleness_penalty: float = 0.0
    _scoring_strategy_override: str | None = None
    if as_of:
        as_of_date = date.fromisoformat(str(as_of))
        age_days = (date.today() - as_of_date).days
        if age_days > MAX_FUNDAMENTAL_AGE_DAYS:
            # Soft penalty: -20 base, -1 per additional day, capped at -50
            extra_days = age_days - MAX_FUNDAMENTAL_AGE_DAYS
            _staleness_penalty = min(20.0 + extra_days, 50.0)
            data_quality_flags.append("stale_data")
            _scoring_strategy_override = "STALE_DATA_DEGRADED"
        elif age_days > STALE_DATA_WARNING_DAYS:
            data_quality_flags.append("stale_data")

    # ── Validate and sanitize row using sector limits (DQ Gates) ──
    row = {
        "pe_ratio": data.get("PE_Ratio") or data.get("pe_ratio"),
        "roe": data.get("ROE%") or data.get("roe"),
        "debt_equity": data.get("Debt_Equity") or data.get("debt_equity"),
        "cfo_pat_ratio": data.get("CFO_PAT_Ratio") or data.get("cfo_pat_ratio"),
        "avg_roe_5y": data.get("Avg_ROE_5Y%") or data.get("avg_roe_5y"),
        "sales_cagr_5y": data.get("Sales_Growth_5Y%") or data.get("sales_cagr_5y"),
        "eps_growth": data.get("EPS_Growth%") or data.get("eps_growth"),
        "promoter_holding": data.get("Promoter_Holding%") or data.get("promoter_holding"),
        "inst_holding": data.get("Inst_Holding%") or data.get("inst_holding"),
        "f_score": data.get("F_Score") or data.get("f_score"),
        "peg_ratio": data.get("PEG_Ratio") or data.get("peg_ratio"),
        "value_gap": data.get("Value_Gap%") or data.get("value_gap"),
        "atr": data.get("ATR") or data.get("atr"),
        "down_from_52w_high": data.get("Down_From_52W_High%") or data.get("down_from_52w_high"),
        "rs_rating": data.get("RS_Rating") or data.get("rs_rating"),
        "symbol": data.get("Symbol") or data.get("symbol"),
    }
    sector = data.get("Sector") or data.get("sector")
    sanitized, _ = validate_record(row, sector=sector)

    # Write back sanitized values to a mutable copy of data
    data = dict(data)
    key_mapping = {
        "pe_ratio": ["PE_Ratio", "pe_ratio"],
        "roe": ["ROE%", "roe"],
        "debt_equity": ["Debt_Equity", "debt_equity"],
        "cfo_pat_ratio": ["CFO_PAT_Ratio", "cfo_pat_ratio"],
        "avg_roe_5y": ["Avg_ROE_5Y%", "avg_roe_5y"],
        "sales_cagr_5y": ["Sales_Growth_5Y%", "sales_cagr_5y"],
        "eps_growth": ["EPS_Growth%", "eps_growth"],
        "promoter_holding": ["Promoter_Holding%", "promoter_holding"],
        "inst_holding": ["Inst_Holding%", "inst_holding"],
        "f_score": ["F_Score", "f_score"],
        "peg_ratio": ["PEG_Ratio", "peg_ratio"],
        "value_gap": ["Value_Gap%", "value_gap"],
        "atr": ["ATR", "atr"],
        "down_from_52w_high": ["Down_From_52W_High%", "down_from_52w_high"],
        "rs_rating": ["RS_Rating", "rs_rating"],
    }
    for k_low, target_keys in key_mapping.items():
        if k_low in sanitized and sanitized[k_low] is not None:
            for tk in target_keys:
                data[tk] = sanitized[k_low]

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

    # Apply staleness penalty (soft gate — degrades score instead of zeroing)
    if _staleness_penalty > 0:
        base_score -= _staleness_penalty
        factor_audit.append({"name": "STALE_DATA_PENALTY", "value": -_staleness_penalty})

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
        "data_quality_flags": data_quality_flags,
        "conviction_score": capped_conviction_score,
        "conviction_boost": conviction["conviction_boost"],
        "institutional_interest": conviction["institutional_interest"],
        "super_investors": ", ".join(conviction["investors"]),
        "scoring_strategy": _scoring_strategy_override or scoring_strategy,
        "factor_penalties": factor_audit,
        "factor_breakdown": _build_factor_breakdown(
            state,
            weights,
            w_sentiment,
            conviction,
            sector_boost,
        ),
    }
