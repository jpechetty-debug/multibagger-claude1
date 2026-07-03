"""
Conviction Engine
-----------------
Calculates a 'Conviction Score' for a given stock based on:
1. Principle Alignment (Does it match our core filters?)
2. Institutional Presence (Is it held by Super Investors?)
3. Growth Quality (Consistency of growth)

This score feeds into the Allocation Engine to determine position sizing.
"""

from .super_investor_registry import get_super_investor_interest


def calculate_conviction_score(stock_data):
    """
    Analyzes stock data and returns a conviction dictionary.

    Expected stock_data keys:
    - symbol
    - sales_growth (float)
    - profit_growth (float)
    - roce (float)
    - debt_to_equity (float)
    - promoter_holding (float)
    - pledge (float)
    """
    score = 0
    max_score = 100
    details = []

    # 1. Institutional Presence (Cloning Layer)
    investors = get_super_investor_interest(stock_data.get("symbol", ""))
    institutional_boost = 0
    if investors:
        institutional_boost = min(15 + (len(investors) * 5), 35)  # Cap to prevent single-factor dominance
        score += institutional_boost
        details.append(f"Super Investors: {', '.join(investors)} (+{institutional_boost})")

    # 2. Principle Alignment (Strategic Filter Layer)
    # ROCE > 20%
    roce = stock_data.get("roce")
    if roce is not None:
        if roce > 25:
            score += 20
            details.append("Excellent ROCE > 25% (+20)")
        elif roce > 18:
            score += 15
            details.append("Good ROCE > 18% (+15)")

    # Growth > 15%
    sales_growth = stock_data.get("sales_growth")
    profit_growth = stock_data.get("profit_growth")

    if sales_growth is not None and profit_growth is not None:
        if sales_growth > 20 and profit_growth > 20:
            score += 25
            details.append("Double Engine Growth > 20% (+25)")
        elif sales_growth > 15:
            score += 15
            details.append("Healthy Sales Growth > 15% (+15)")

    # 3. Governance/Safety (Risk Layer)
    d2e = stock_data.get("debt_to_equity")
    pledge = stock_data.get("pledge")

    if d2e is not None:
        if d2e < 0.1:
            score += 15
            details.append("Debt Free (+15)")
        elif d2e < 0.5:
            score += 10
            details.append("Low Debt (+10)")

    if pledge is not None:
        if pledge == 0:
            score += 10
            details.append("Zero Pledge (+10)")
        elif pledge <= 5:
            # Minor / administrative pledge — SEBI watch-list threshold.
            # Consistent with promoter_intel.py "pledge_current < 5" buy-signal boundary.
            score -= 5
            details.append("Minor Pledge <=5% (-5)")
        elif pledge <= 20:
            # Moderate concern — insider.py flags pledge > 5 as a warning,
            # score_diagnostics.py marks pledge > 10 as high-impact.
            score -= 12
            details.append("Moderate Pledge <=20% (-12)")
        elif pledge <= 50:
            # High risk — risk.py treats pledge > 25 as a governance red flag.
            score -= 20
            details.append("High Pledge <=50% (-20)")
        else:
            # Severe — SEBI CIR/CFD/CMD1/168/2019 mandatory-action territory.
            score -= 25
            details.append("Critical Pledge >50% (-25)")

    # Cap and floor: conviction score must stay in [0, max_score].
    # Without the floor, a stock with minimal positives and any pledge can
    # produce a negative conviction_score that propagates into the scoring
    # engine's capped_conviction_score and the GARP rank_score, silently
    # deflating the final score with no transparency to the user.
    final_score = max(0, min(score, max_score))

    return {
        "conviction_score": final_score,
        "institutional_interest": bool(investors),
        "investors": investors,
        "details": details,
        "conviction_boost": round(
            institutional_boost / 100.0, 2
        ),  # e.g. 0.15 for allocation multiplier
    }
