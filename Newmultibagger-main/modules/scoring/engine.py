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
from modules.field_names import normalize_data_keys
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
        "roce": safe_float(data.get("ROCE%")),
        "debt_to_equity": safe_float(data.get("Debt_Equity")),
        "promoter_holding": safe_float(data.get("Promoter_Holding%")),
        "pledge": safe_float(data.get("Pledge_Pct")),
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
    # ── Canonicalize all incoming keys to Title-case once ──────────────────
    # Callers may pass either screener-style Title-case keys ("Sales_Growth_5Y%")
    # or DB-read snake_case keys ("sales_cagr_5y").  Normalizing here means every
    # downstream access — factors, adjustments, ceiling — can use a single key
    # with no "or" fallbacks.
    data = normalize_data_keys(data)

    # ── Extract shared date fields once ──
    as_of = data.get("As_Of_Date")
    quarter_end = data.get("Quarter_End")

    # ── Data quality tracking (initialised before gates so gates can append) ──
    data_quality_flags: list[str] = []
    _staleness_penalty: float = 0.0
    _scoring_strategy_override: str | None = None

    # ── PIT hard gate: block scoring if data is too fresh (SEBI 45-day lag) ──
    if quarter_end and as_of:
        enforce_pit_gate(as_of, quarter_end, symbol=data.get("Symbol", "UNKNOWN"))
    else:
        data_quality_flags.append("PIT_GATE_SKIPPED_MISSING_DATES")
    if as_of:
        try:
            as_of_date = date.fromisoformat(str(as_of))
        except (ValueError, TypeError):
            as_of_date = None
            data_quality_flags.append("unparseable_as_of_date")
        if as_of_date is not None:
            age_days = (date.today() - as_of_date).days
            if age_days > MAX_FUNDAMENTAL_AGE_DAYS:
                # Soft penalty: -20 base, -1 per additional day, capped at -50
                extra_days = age_days - MAX_FUNDAMENTAL_AGE_DAYS
                _staleness_penalty = min(20.0 + extra_days, 50.0)
                data_quality_flags.append("stale_data")
                _scoring_strategy_override = "STALE_DATA_DEGRADED"

                try:
                    from worker.tasks import refresh_stale_data
                    refresh_stale_data.delay(data.get("Symbol", "UNKNOWN"))
                except Exception:
                    pass  # Do not block scoring if task dispatch fails
            elif age_days > STALE_DATA_WARNING_DAYS:
                data_quality_flags.append("stale_data")

    # ── Validate and sanitize row using sector limits (DQ Gates) ──
    # Keys are already canonical after normalize_data_keys(); build the
    # lowercase DQ-gate dict directly from canonical keys.
    row = {
        "pe_ratio": data.get("PE_Ratio"),
        "roe": data.get("ROE%"),
        "debt_equity": data.get("Debt_Equity"),
        "cfo_pat_ratio": data.get("CFO_PAT_Ratio"),
        "avg_roe_5y": data.get("Avg_ROE_5Y%"),
        "sales_cagr_5y": data.get("Sales_Growth_5Y%"),
        "eps_growth": data.get("EPS_Growth%"),
        "promoter_holding": data.get("Promoter_Holding%"),
        "inst_holding": data.get("Inst_Holding%"),
        "f_score": data.get("F_Score"),
        "peg_ratio": data.get("PEG_Ratio"),
        "value_gap": data.get("Value_Gap%"),
        "atr": data.get("ATR"),
        "down_from_52w_high": data.get("Down_From_52W_High%"),
        "rs_rating": data.get("RS_Rating"),
        "symbol": data.get("Symbol"),
    }
    sector = data.get("Sector")
    sanitized, _ = validate_record(row, sector=sector)

    # Write sanitized values back using canonical keys only.
    # One dict copy, no O(N×M) loop over a key_mapping table.
    data = dict(data)
    _sanitized_to_canonical = {
        "pe_ratio": "PE_Ratio",
        "roe": "ROE%",
        "debt_equity": "Debt_Equity",
        "cfo_pat_ratio": "CFO_PAT_Ratio",
        "avg_roe_5y": "Avg_ROE_5Y%",
        "sales_cagr_5y": "Sales_Growth_5Y%",
        "eps_growth": "EPS_Growth%",
        "promoter_holding": "Promoter_Holding%",
        "inst_holding": "Inst_Holding%",
        "f_score": "F_Score",
        "peg_ratio": "PEG_Ratio",
        "value_gap": "Value_Gap%",
        "atr": "ATR",
        "down_from_52w_high": "Down_From_52W_High%",
        "rs_rating": "RS_Rating",
    }
    for dq_key, canonical_key in _sanitized_to_canonical.items():
        if dq_key in sanitized and sanitized[dq_key] is not None:
            data[canonical_key] = sanitized[dq_key]

    resolved_mode, weights, scoring_strategy = _resolve_mode_and_weights(market_regime, sector=data.get("Sector", ""))
    score_sentiment, w_sentiment = _calculate_sentiment_factor(data, weights)
    state = _build_factor_state(data, score_sentiment, scoring_mode=resolved_mode)
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

    # Phase 2.2: Proportional bonus cap — max 18 points or 20% of base_score,
    # whichever is smaller. Prevents non-fundamental inflation.
    # Floor at 5 so low-scoring stocks aren't doubly penalised
    max_bonus = min(18.0, max(5.0, base_score * 0.20))
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

    for disqualifier_name, cap_val in disqualifiers:
        factor_audit.append({"name": disqualifier_name, "value": round(cap_val - 100, 1)})

    raw_score = round(max(0, min(base_score, 100.0)), 1)

    # Cap institutional conviction score so it doesn't bypass the fundamental score ceiling
    capped_conviction_score = min(conviction["conviction_score"], score_ceiling, max(final_score, 0))

    result = {
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

    try:
        from modules.ic_monitor import load_regime_ic_cache, get_current_regime
        current_regime = get_current_regime()
        regime_ic_data = load_regime_ic_cache().get(current_regime, {})
        if regime_ic_data and not regime_ic_data.get("valid", True):
            result["data_quality_flags"].append("low_regime_ic")
            result["regime_ic_warning"] = (
                f"IC={regime_ic_data['ic']:.3f} in {current_regime} regime "
                f"(n={regime_ic_data['n']}) — signal confidence is low"
            )
    except ImportError:
        pass

    return result
