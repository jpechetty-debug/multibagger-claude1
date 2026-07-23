"""
Inflection Detector
====================
Detects earnings, margin, and momentum inflection points in stock data.

These signals are the #1 predictor of multibagger re-rating:
when a company's earnings trajectory shifts from decelerating to
accelerating, the stock typically re-rates 50-300% over 6-18 months.

Uses PIT (Point-In-Time) data from the database and pre-computed metrics
from the scoring pipeline. No yfinance dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.observability.logger import get_logger

_log = get_logger(__name__)


@dataclass
class InflectionResult:
    """Result of inflection analysis for a stock."""

    symbol: str
    earnings_inflection: bool
    margin_inflection: bool
    momentum_inflection: bool
    inflection_score: int  # 0-10
    inflection_tier: str  # "NONE", "WEAK", "MODERATE", "STRONG", "EXPLOSIVE"
    details: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "earnings_inflection": self.earnings_inflection,
            "margin_inflection": self.margin_inflection,
            "momentum_inflection": self.momentum_inflection,
            "inflection_score": self.inflection_score,
            "inflection_tier": self.inflection_tier,
            "details": self.details,
        }


def _sf(val, default=0.0) -> float:
    """Safe float conversion."""
    if val is None:
        return default
    try:
        result = float(val)
        return default if result != result else result  # NaN check
    except (ValueError, TypeError):
        return default


def _get(data: dict, *keys, default=0.0):
    """Multi-key lookup with fallback."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            return _sf(val, default)
    return default


# ---------------------------------------------------------------------------
# Core inflection detectors
# ---------------------------------------------------------------------------

def _detect_earnings_inflection(data: dict) -> tuple[bool, int, list[str]]:
    """
    Detect if earnings are inflecting upward.

    Signals:
    - EPS growth accelerating (current > historical)
    - PAT CAGR 3Y > PAT CAGR 5Y (recent growth faster)
    - Positive EPS growth after negative/flat period
    """
    score = 0
    details: list[str] = []

    eps_g = _get(data, "EPS_Growth%", "eps_growth")
    pat_3y = _get(data, "PAT_CAGR_3Y")
    pat_5y = _get(data, "PAT_CAGR_5Y")

    # Signal 1: Absolute EPS growth > 20%
    if eps_g > 40:
        score += 3
        details.append(f"Strong EPS growth: {eps_g:.0f}%")
    elif eps_g > 20:
        score += 2
        details.append(f"Healthy EPS growth: {eps_g:.0f}%")
    elif eps_g > 10:
        score += 1
        details.append(f"Moderate EPS growth: {eps_g:.0f}%")

    # Signal 2: Earnings acceleration — 3Y growth > 5Y growth
    if pat_3y > 0 and pat_5y > 0:
        if pat_3y > pat_5y * 1.3:
            score += 2
            details.append(f"Earnings accelerating: 3Y={pat_3y:.0f}% > 5Y={pat_5y:.0f}%")
        elif pat_3y > pat_5y:
            score += 1
            details.append(f"Earnings stable: 3Y={pat_3y:.0f}% ≈ 5Y={pat_5y:.0f}%")
    elif pat_3y > 20 and pat_5y <= 0:
        # Turnaround — was declining, now growing
        score += 3
        details.append(f"Earnings turnaround: 3Y={pat_3y:.0f}% (was declining)")

    # Signal 3: Earnings Inflection Score (pre-computed if available)
    infl_score = _get(data, "Earnings_Inflection_Score")
    if infl_score >= 4:
        score += 2
        details.append(f"Inflection Score: {infl_score:.0f}/5")
    elif infl_score >= 2:
        score += 1

    has_inflection = score >= 3
    return has_inflection, score, details


def _detect_margin_inflection(data: dict) -> tuple[bool, int, list[str]]:
    """
    Detect if operating margins are inflecting upward.

    This is the "operating leverage" signal — when a company's costs
    grow slower than revenue, margins expand, and EPS grows faster
    than revenue. This is the mechanism behind most multibagger re-ratings.
    """
    score = 0
    details: list[str] = []

    opm = _get(data, "Operating_Margin%", "opm")
    avg_opm = _get(data, "Avg_OPM_5Y%", "avg_opm_5y")
    _get(data, "Profit_Margin%")
    roce = _get(data, "ROCE%", "roce")

    # Signal 1: Current OPM > 5Y average OPM (margin expansion)
    if avg_opm > 0 and opm > 0:
        margin_expansion = opm - avg_opm
        if margin_expansion > 5:
            score += 3
            details.append(f"Strong margin expansion: +{margin_expansion:.1f}pp")
        elif margin_expansion > 2:
            score += 2
            details.append(f"Moderate margin expansion: +{margin_expansion:.1f}pp")
        elif margin_expansion > 0:
            score += 1
            details.append(f"Slight margin improvement: +{margin_expansion:.1f}pp")

    # Signal 2: High absolute margin (industry leader)
    if opm > 25:
        score += 1
        details.append(f"Premium margins: {opm:.0f}%")

    # Signal 3: ROCE improving (capital efficiency)
    if roce > 25:
        score += 1
        details.append(f"High ROCE: {roce:.0f}%")

    # Signal 4: Operating leverage — EPS growth >> Revenue growth
    eps_g = _get(data, "EPS_Growth%", "eps_growth")
    sg = _get(data, "Sales_Growth_TTM%", "sales_growth")
    if sg > 5 and eps_g > sg * 1.5:
        score += 2
        details.append(f"Operating leverage: EPS +{eps_g:.0f}% vs Rev +{sg:.0f}%")

    has_inflection = score >= 3
    return has_inflection, score, details


def _detect_momentum_inflection(data: dict) -> tuple[bool, int, list[str]]:
    """
    Detect if price/volume momentum is confirming fundamental improvement.

    When fundamentals improve AND price/volume confirm, the probability
    of a sustained move increases significantly.
    """
    score = 0
    details: list[str] = []

    # Signal 1: Volume breakout
    vol_breakout = _get(data, "Vol_Breakout")
    if vol_breakout > 3.0:
        score += 2
        details.append(f"Strong volume breakout: {vol_breakout:.1f}x avg")
    elif vol_breakout > 2.0:
        score += 1
        details.append(f"Volume pickup: {vol_breakout:.1f}x avg")

    # Signal 2: RS Rating (relative strength vs market)
    rs = _get(data, "RS_Rating", "rs_rating")
    if rs > 80:
        score += 2
        details.append(f"Strong RS Rating: {rs:.0f}")
    elif rs > 60:
        score += 1
        details.append(f"Above-average RS: {rs:.0f}")

    # Signal 3: Not far from 52W high (trend intact)
    down = _get(data, "Down_From_52W_High%", "down_from_52w")
    if 0 < down <= 10:
        score += 1
        details.append(f"Near 52W high ({down:.0f}% off)")
    elif down > 30:
        # Could be opportunity if fundamentals strong — no penalty but no bonus
        pass

    # Signal 4: Technical signal
    tech = data.get("Technical_Signal", "")
    if tech == "Bullish":
        score += 1
        details.append("Bullish technical pattern")

    # Signal 5: Institutional accumulation
    inst = _get(data, "Inst_Holding%")
    if inst > 20:
        score += 1
        details.append(f"Institutional backing: {inst:.0f}%")

    has_inflection = score >= 3
    return has_inflection, score, details


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_inflection(stock_data: dict) -> InflectionResult:
    """
    Run full inflection detection on a stock.

    Returns an InflectionResult with:
    - Individual inflection flags (earnings, margin, momentum)
    - Combined inflection score (0-10)
    - Inflection tier classification
    """
    symbol = stock_data.get("Symbol", stock_data.get("symbol", "UNKNOWN"))

    earnings_infl, earn_score, earn_details = _detect_earnings_inflection(stock_data)
    margin_infl, margin_score, margin_details = _detect_margin_inflection(stock_data)
    momentum_infl, mom_score, mom_details = _detect_momentum_inflection(stock_data)

    # Combined score — weighted toward earnings (most predictive)
    combined = min(10, round(earn_score * 0.45 + margin_score * 0.30 + mom_score * 0.25))

    # Tier classification
    if combined >= 8:
        tier = "EXPLOSIVE"
    elif combined >= 6:
        tier = "STRONG"
    elif combined >= 4:
        tier = "MODERATE"
    elif combined >= 2:
        tier = "WEAK"
    else:
        tier = "NONE"

    all_details = earn_details + margin_details + mom_details

    return InflectionResult(
        symbol=symbol,
        earnings_inflection=earnings_infl,
        margin_inflection=margin_infl,
        momentum_inflection=momentum_infl,
        inflection_score=combined,
        inflection_tier=tier,
        details=all_details,
    )


def get_inflection_score(stock_data: dict) -> int:
    """Quick accessor — returns just the combined inflection score (0-10)."""
    result = detect_inflection(stock_data)
    return result.inflection_score


def is_inflecting(stock_data: dict) -> bool:
    """Quick check — is this stock at an earnings/margin inflection point?"""
    result = detect_inflection(stock_data)
    return result.inflection_score >= 4
