"""
Super Investor Registry
-----------------------
Tracks high-conviction holdings of renowned Indian super-investors.
This acts as a "Cloning Source" for the Conviction Engine.

NOTE: This registry should be updated quarterly based on shareholding patterns.
"""

import warnings
import calendar
from datetime import date

REGISTRY_AS_OF = "2026-Q2"

REGISTRY_SOURCES = {
    "DOLLY_KHANNA": "https://trendlyne.com/portfolio/superstar-shareholders/custom/?query=Dolly+Khanna",
    "ASHISH_KACHOLIA": "https://www.solomoney.in/ashish-kacholia-portfolio/",
    "VIJAY_KEDIA": "https://money.rediff.com/companies/vijay-kumar-kedia/11051676",
    "MUKUL_AGRAWAL": "https://trendlyne.com/portfolio/superstar-shareholders/custom/?query=Mukul+Mahavir+Agrawal",
    "SUNIL_SINGHANIA": "https://money.rediff.com/companies/sunil-singhania/11052153",
}


def _registry_quarter_end(label: str) -> date:
    year, quarter = label.split("-Q")
    month = int(quarter) * 3
    return date(int(year), month, calendar.monthrange(int(year), month)[1])


def _check_registry_staleness(today: date | None = None):
    """Emit a runtime warning if the registry is older than 120 days."""
    try:
        registry_date = _registry_quarter_end(REGISTRY_AS_OF)
        age_days = ((today or date.today()) - registry_date).days
        if age_days > 120:
            warnings.warn(
                f"Super investor registry is {age_days} days old "
                f"(REGISTRY_AS_OF={REGISTRY_AS_OF}). Update from SEBI shareholding data.",
                UserWarning,
                stacklevel=2,
            )
    except (ValueError, KeyError):
        pass

_check_registry_staleness()

SUPER_INVESTORS = {
    "DOLLY_KHANNA": {
        "style": "Momentum + Value in Smallcaps",
        "holdings": [
            "CHENNPETRO.NS",
            "SAVERA.NS",
            "PRAKASH.NS",
        ],
    },
    "ASHISH_KACHOLIA": {
        "style": "High Growth Small/Midcaps",
        "holdings": [
            "SHAILY.NS",
            "KMEW.BO",
            "SAFARI.NS",
            "XPROINDIA.NS",
            "AEROFLEX.NS",
        ],
    },
    "VIJAY_KEDIA": {
        "style": "Turnaround + Niche Management",
        "holdings": [
            "ELECON.NS",
            "SIYSIL.NS",
            "SUDARSCHEM.NS",
            "MHRIL.NS",
            "GLOBALVECT.NS",
            "AFFORDABLE.NS",
            "WEBELSOLAR.NS",
            "REPRO.NS",
        ],
    },
    "MUKUL_AGRAWAL": {
        "style": "Aggressive Growth / Defense / Rail",
        "holdings": [
            "AJMERA.NS",
            "J&KBANK.NS",
            "JKIL.NS",
            "MONOLITH.NS",
            "LAXMIINDIA.NS",
            "ARISINFRA.NS",
        ],
    },
    "SUNIL_SINGHANIA": {
        "style": "Institutional Quality at Fair Price",
        "holdings": [
            "CARYSIL.NS",
            "ANUP.NS",
            "DYNAMATECH.NS",
            "TIIL.NS",
            "TTKHLTCARE.NS",
            "IONEXCHANG.NS",
            "RUPA.NS",
            "SIYSIL.NS",
            "HGINFRA.NS",
            "MASTEK.NS",
            "JUBLPHARMA.NS",
            "SUVEN.NS",
        ],
    },
}


def get_super_investor_interest(symbol):
    """
    Returns a list of investors holding the stock.
    Example: ['DOLLY_KHANNA', 'VIJAY_KEDIA']
    """
    interested_investors = []
    symbol = symbol.upper()

    # Normalize symbol (handle .NS extension)
    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol_ns = f"{symbol}.NS"
    else:
        symbol_ns = symbol

    for investor, data in SUPER_INVESTORS.items():
        # Check both raw and NS versions
        if symbol in data["holdings"] or symbol_ns in data["holdings"]:
            interested_investors.append(investor)

    return interested_investors
