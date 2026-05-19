"""
Scoring — Institutional score orchestrator.

This is the top-level engine that composes factor computation, adjustments,
ceiling rules, and conviction scoring into the final composite score.
"""

from __future__ import annotations

import hashlib
from typing import Any

from modules.data_utils import safe_float
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
