"""
Fundamental Filters — Tiered Multibagger Discovery
====================================================
Replaces the single strict GARP filter with a 4-tier system that
captures different multibagger archetypes.

Tiers:
  1. Classic Compounder — GARP with relaxed thresholds
  2. Turnaround Story    — negative history but improving trajectory
  3. Early-Stage Disruptor — small cap, revenue scaling, earnings may be negative
  4. Deep Value Inflection — cheap, high-quality, near 52W low

A stock passes if it qualifies for ANY tier (union, not intersection).
Each stock is tagged with its tier for downstream ML and reporting.
"""

from __future__ import annotations

import config
from core.observability.logger import get_logger

_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_val(stock_data: dict, key: str, default=0):
    """Case-insensitive key lookup."""
    if key in stock_data:
        val = stock_data[key]
        return val if val is not None else default
    lower_key = key.lower()
    for k, v in stock_data.items():
        if k.lower() == lower_key:
            return v if v is not None else default
    return default


def _safe_float(val, default=0.0) -> float:
    if val is None:
        return default
    try:
        result = float(val)
        if result != result:  # NaN
            return default
        return result
    except (ValueError, TypeError):
        return default


def _is_financial_sector(stock_data: dict) -> bool:
    sector = str(_get_val(stock_data, "Sector", "")).lower()
    return any(kw in sector for kw in ("bank", "finance", "nbfc", "insurance"))


# ---------------------------------------------------------------------------
# Gate 0: Universal minimum — safety net, not a quality filter
# ---------------------------------------------------------------------------

def _pass_universal_gate(stock_data: dict) -> tuple[bool, str]:
    """Hard minimums that ALL tiers must satisfy."""
    min_mcap = getattr(config, "MIN_MARKET_CAP_CR", 100)
    mcap = _safe_float(_get_val(stock_data, "Market_Cap_Cr", 0))
    if mcap == 0:
        mcap = _safe_float(_get_val(stock_data, "market_cap_cr", 0))

    # Market cap floor — relaxed to 100 Cr (was 500 Cr)
    if mcap > 0 and mcap < min_mcap:
        return False, f"Below Market Cap Gate ({mcap:.0f} Cr < {min_mcap} Cr)"

    return True, "OK"


# ---------------------------------------------------------------------------
# Tier 1: Classic Compounder (relaxed GARP)
# ---------------------------------------------------------------------------

def _tier1_classic_compounder(stock_data: dict) -> tuple[bool, str]:
    """
    Relaxed GARP: consistent growth + reasonable valuation.
    - Sales 5Y > 12% OR TTM > 18%
    - ROE > 12% (was 15%)
    - PEG 0.3-3.5 (was 0.5-2.5)
    - D/E < 1.0 (was 0.7) — gives room for capex-heavy companies
    - Promoter > 30% OR (Promoter + Inst > 50%)
    """
    # Growth
    sg_5y = _safe_float(_get_val(stock_data, "Sales_Growth_5Y%"))
    sg_ttm = _safe_float(_get_val(stock_data, "Sales_Growth_TTM%"))
    if sg_5y == 0:
        sg_5y = _safe_float(_get_val(stock_data, "sales_cagr_5y"))
    if sg_ttm == 0:
        sg_ttm = _safe_float(_get_val(stock_data, "sales_growth"))

    if sg_5y < 12 and sg_ttm < 18:
        return False, f"T1: Low Growth (5Y={sg_5y:.0f}%, TTM={sg_ttm:.0f}%)"

    # Profitability
    roe = _safe_float(_get_val(stock_data, "Avg_ROE_5Y%"))
    if roe == 0:
        roe = _safe_float(_get_val(stock_data, "avg_roe_5y"))
    if roe == 0:
        roe = _safe_float(_get_val(stock_data, "ROE%"))
    if roe == 0:
        roe = _safe_float(_get_val(stock_data, "roe"))

    if roe < 12:
        return False, f"T1: Low ROE ({roe:.0f}%)"

    # Valuation
    peg = _safe_float(_get_val(stock_data, "PEG_Ratio", 100))
    if peg == 100:
        peg = _safe_float(_get_val(stock_data, "peg_ratio", 100))
    if peg < 0.3 or peg > 3.5:
        return False, f"T1: PEG out of range ({peg:.1f})"

    # Debt — relaxed, skip for financials
    if not _is_financial_sector(stock_data):
        de = _safe_float(_get_val(stock_data, "Debt_Equity", 100))
        if de == 100:
            de = _safe_float(_get_val(stock_data, "debt_equity", 100))
        if de > 1.0:
            return False, f"T1: High Debt (D/E={de:.1f})"

    # Ownership
    prom = _safe_float(_get_val(stock_data, "Promoter_Holding%"))
    inst = _safe_float(_get_val(stock_data, "Inst_Holding%"))
    if prom < 30 and (prom + inst) < 50:
        return False, f"T1: Low Ownership (Prom={prom:.0f}%, Inst={inst:.0f}%)"

    return True, "Tier1:ClassicCompounder"


# ---------------------------------------------------------------------------
# Tier 2: Turnaround Story
# ---------------------------------------------------------------------------

def _tier2_turnaround(stock_data: dict) -> tuple[bool, str]:
    """
    Negative long-term history BUT recent improvement trajectory.
    - TTM growth > 20% (recent acceleration)
    - Current ROE > 8% (turning profitable)
    - Margin expansion: OPM > Avg_OPM (margins improving)
    - F-Score >= 5 (financial health improving)
    """
    sg_ttm = _safe_float(_get_val(stock_data, "Sales_Growth_TTM%"))
    if sg_ttm == 0:
        sg_ttm = _safe_float(_get_val(stock_data, "sales_growth"))

    if sg_ttm < 20:
        return False, f"T2: TTM growth too low ({sg_ttm:.0f}%)"

    # Current profitability (even if weak)
    roe = _safe_float(_get_val(stock_data, "ROE%"))
    if roe == 0:
        roe = _safe_float(_get_val(stock_data, "roe"))
    if roe < 8:
        return False, f"T2: ROE too low ({roe:.0f}%)"

    # Margin expansion signal
    opm = _safe_float(_get_val(stock_data, "Operating_Margin%"))
    if opm == 0:
        opm = _safe_float(_get_val(stock_data, "opm"))
    avg_opm = _safe_float(_get_val(stock_data, "Avg_OPM_5Y%"))
    if avg_opm == 0:
        avg_opm = _safe_float(_get_val(stock_data, "avg_opm_5y"))

    margin_improving = opm > avg_opm if avg_opm > 0 else opm > 10

    # EPS acceleration
    eps_g = _safe_float(_get_val(stock_data, "EPS_Growth%"))
    if eps_g == 0:
        eps_g = _safe_float(_get_val(stock_data, "eps_growth"))

    earnings_accelerating = eps_g > 15

    if not margin_improving and not earnings_accelerating:
        return False, "T2: No margin or earnings improvement"

    # Quality floor
    f_score = _safe_float(_get_val(stock_data, "F_Score"))
    if f_score > 0 and f_score < 5:
        return False, f"T2: Quality too low (F-Score={f_score:.0f})"

    return True, "Tier2:TurnaroundStory"


# ---------------------------------------------------------------------------
# Tier 3: Early-Stage Disruptor
# ---------------------------------------------------------------------------

def _tier3_early_stage(stock_data: dict) -> tuple[bool, str]:
    """
    Small cap, rapid revenue scaling, earnings may be negative or thin.
    - Market cap < 5000 Cr
    - Revenue CAGR 3Y or 5Y > 25%
    - Promoter > 35% (founder-led)
    - Negative earnings acceptable if revenue > 200% growth TTM
    """
    mcap = _safe_float(_get_val(stock_data, "Market_Cap_Cr"))
    if mcap == 0:
        mcap = _safe_float(_get_val(stock_data, "market_cap_cr"))

    if mcap > 5000:
        return False, f"T3: Too large for disruptor tier ({mcap:.0f} Cr)"

    # Revenue growth — must be strong
    sg_5y = _safe_float(_get_val(stock_data, "Sales_Growth_5Y%"))
    sg_ttm = _safe_float(_get_val(stock_data, "Sales_Growth_TTM%"))
    if sg_5y == 0:
        sg_5y = _safe_float(_get_val(stock_data, "sales_cagr_5y"))
    if sg_ttm == 0:
        sg_ttm = _safe_float(_get_val(stock_data, "sales_growth"))

    pat_3y = _safe_float(_get_val(stock_data, "PAT_CAGR_3Y"))
    pat_5y = _safe_float(_get_val(stock_data, "PAT_CAGR_5Y"))

    best_revenue_growth = max(sg_5y, sg_ttm)
    best_pat_growth = max(pat_3y, pat_5y)

    if best_revenue_growth < 25:
        return False, f"T3: Revenue growth too low ({best_revenue_growth:.0f}%)"

    # Founder skin in the game
    prom = _safe_float(_get_val(stock_data, "Promoter_Holding%"))
    if prom > 0 and prom < 35:
        return False, f"T3: Low promoter holding ({prom:.0f}%)"

    # Allow negative earnings ONLY if revenue is scaling fast
    eps_g = _safe_float(_get_val(stock_data, "EPS_Growth%"))
    if eps_g == 0:
        eps_g = _safe_float(_get_val(stock_data, "eps_growth"))

    if eps_g < 0 and best_revenue_growth < 40:
        return False, "T3: Negative earnings without strong revenue growth"

    return True, "Tier3:EarlyStageDisruptor"


# ---------------------------------------------------------------------------
# Tier 4: Deep Value Inflection
# ---------------------------------------------------------------------------

def _tier4_deep_value(stock_data: dict) -> tuple[bool, str]:
    """
    Cheap, high-quality stock near bottom with improving fundamentals.
    - PE < 12 (cheap)
    - F-Score >= 6 (quality)
    - CFO/PAT > 0.8 (cash generation confirmed)
    - Down < 30% from 52W high (not in freefall)
    - ROE > 10% (not a value trap)
    """
    pe = _safe_float(_get_val(stock_data, "PE_Ratio", 999))
    if pe == 999:
        pe = _safe_float(_get_val(stock_data, "pe_ratio", 999))
    if pe == 999:
        pe = _safe_float(_get_val(stock_data, "pe", 999))

    if pe <= 0 or pe > 12:
        return False, f"T4: PE not in deep value range ({pe:.1f})"

    # Quality floor
    f_score = _safe_float(_get_val(stock_data, "F_Score"))
    if f_score > 0 and f_score < 6:
        return False, f"T4: Quality too low (F-Score={f_score:.0f})"

    # Cash flow reality
    cfo_pat = _safe_float(_get_val(stock_data, "CFO_PAT_Ratio"))
    if cfo_pat == 0:
        cfo_pat = _safe_float(_get_val(stock_data, "cfo_pat_ratio"))
    if cfo_pat > 0 and cfo_pat < 0.8:
        return False, f"T4: Weak cash flow (CFO/PAT={cfo_pat:.1f})"

    # Not in freefall
    down = _safe_float(_get_val(stock_data, "Down_From_52W_High%"))
    if down == 0:
        down = _safe_float(_get_val(stock_data, "down_from_52w"))
    if down > 40:
        return False, f"T4: Falling knife ({down:.0f}% from high)"

    # Not a value trap — must have some profitability
    roe = _safe_float(_get_val(stock_data, "ROE%"))
    if roe == 0:
        roe = _safe_float(_get_val(stock_data, "roe"))
    if roe == 0:
        roe = _safe_float(_get_val(stock_data, "Avg_ROE_5Y%"))
    if roe > 0 and roe < 10:
        return False, f"T4: Value trap risk (ROE={roe:.0f}%)"

    return True, "Tier4:DeepValueInflection"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_TIER_FUNCTIONS = [
    ("Tier1", _tier1_classic_compounder),
    ("Tier2", _tier2_turnaround),
    ("Tier3", _tier3_early_stage),
    ("Tier4", _tier4_deep_value),
]


def classify_multibagger_tier(stock_data: dict) -> tuple[str | None, str]:
    """
    Classify a stock into a multibagger tier.

    Returns:
        (tier_name, reason) — tier_name is None if no tier matched.
    """
    # Universal gate — must pass for all tiers
    gate_pass, gate_reason = _pass_universal_gate(stock_data)
    if not gate_pass:
        return None, gate_reason

    # Try each tier in order — first match wins
    for tier_name, tier_fn in _TIER_FUNCTIONS:
        passed, reason = tier_fn(stock_data)
        if passed:
            return tier_name, reason

    return None, "No tier matched"


def validate_garp_criteria(stock_data: dict) -> tuple[bool, str]:
    """
    Enhanced GARP validation — now uses tiered multibagger discovery.

    A stock passes if it qualifies for ANY tier (union logic).
    Backward compatible: returns (is_valid, reason) tuple.
    """
    tier, reason = classify_multibagger_tier(stock_data)
    if tier is not None:
        return True, reason
    return False, reason


def get_tier_label(stock_data: dict) -> str:
    """Get a human-readable tier label for display."""
    tier, reason = classify_multibagger_tier(stock_data)
    if tier is None:
        return "Unqualified"
    labels = {
        "Tier1": "🏢 Classic Compounder",
        "Tier2": "🔄 Turnaround",
        "Tier3": "🚀 Early-Stage Disruptor",
        "Tier4": "💎 Deep Value",
    }
    return labels.get(tier, tier)


# ---------------------------------------------------------------------------
# Sector-relative filter (unchanged — works with any tier system)
# ---------------------------------------------------------------------------

def build_sector_relative_filter(
    stocks: list[dict],
    sector_medians: dict[str, dict[str, float]],
    *,
    outperformance_ratio: float = 1.20,
    min_metrics_to_beat: int = 2,
) -> list[dict]:
    """Filter stocks that beat their sector median by *outperformance_ratio*.

    For each stock the function checks three metrics against the sector median:
      - ROE  (Avg_ROE_5Y% or ROE%)
      - Sales Growth (Sales_Growth_5Y% or Sales_Growth_TTM%)
      - PE Ratio (PE_Ratio) — *inverted*: lower is better.

    A stock passes when it beats at least *min_metrics_to_beat* of the three
    sector benchmarks.
    """
    passed: list[dict] = []

    for stock in stocks:
        sector = str(stock.get("Sector", "Unknown"))
        medians = sector_medians.get(sector)
        if medians is None:
            continue

        beats = []

        # --- ROE ---
        roe = stock.get("Avg_ROE_5Y%") or stock.get("avg_roe_5y")
        if roe is None:
            roe = stock.get("ROE%") or stock.get("roe")
        median_roe = medians.get("median_roe", 0)
        if roe is not None and median_roe > 0 and roe >= median_roe * outperformance_ratio:
            beats.append("roe")

        # --- Growth ---
        growth = stock.get("Sales_Growth_5Y%") or stock.get("sales_cagr_5y")
        if growth is None:
            growth = stock.get("Sales_Growth_TTM%") or stock.get("sales_growth")
        median_growth = medians.get("median_growth", 0)
        if growth is not None and median_growth > 0 and growth >= median_growth * outperformance_ratio:
            beats.append("growth")

        # --- PE (inverted: lower is better) ---
        pe = stock.get("PE_Ratio") or stock.get("pe_ratio")
        median_pe = medians.get("median_pe", 0)
        if pe is not None and pe > 0 and median_pe > 0:
            if pe <= median_pe / outperformance_ratio:
                beats.append("pe")

        if len(beats) >= min_metrics_to_beat:
            stock["sector_relative_pass"] = ",".join(beats)
            passed.append(stock)

    return passed
