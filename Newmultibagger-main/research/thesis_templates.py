"""
Sovereign AI Trading Engine v4.0 — Thesis Templates
Defines standard templates for generating investment memos.
"""

from typing import Dict

COMPOUNDER_TEMPLATE = """
# Investment Thesis: Compounder

## Core Premise
Why will this company structurally compound earnings at {expected_cagr}% over the next {horizon_years} years?

## Reinvestment Runway
What is the size of the opportunity and the company's ability to reinvest capital at high rates of return?

## Moat & Competitive Advantage
What protects this business from competition? (Brand, switching costs, network effects, cost advantage)

## Disconfirming Evidence
What breaks this thesis? (What would make us sell?)
"""

TURNAROUND_TEMPLATE = """
# Investment Thesis: Turnaround

## The Catalyst
What is fundamentally changing? (Management change, industry cycle, debt reduction, margin normalization)

## Proof of Success
What metrics prove the turnaround is working?

## Disconfirming Evidence
What invalidates this idea and indicates the business is in structural decline rather than a temporary slump?
"""

CYCLICAL_TEMPLATE = """
# Investment Thesis: Cyclical

## Cycle Positioning
Where are we in the current industry cycle? (Bottom, mid-cycle, peak)

## Normalized Earnings
What are the normalized earnings across a full cycle, and what is the current valuation based on that?

## Disconfirming Evidence
What signals a turn in the cycle that would force an exit?
"""

TEMPLATES: Dict[str, str] = {
    "Compounder": COMPOUNDER_TEMPLATE,
    "Turnaround": TURNAROUND_TEMPLATE,
    "Cyclical": CYCLICAL_TEMPLATE
}

def get_template(template_type: str, **kwargs) -> str:
    """
    Returns a formatted template.
    """
    template = TEMPLATES.get(template_type, COMPOUNDER_TEMPLATE)
    try:
        return template.format(**kwargs)
    except KeyError:
        # If kwargs are missing, just return the raw template
        return template
