"""
research/compounder_registry.py

Registry of historical compounders used for Compounder Capture Rate validation.
Stored here temporarily; will be migrated to SQLite.
"""

from typing import Dict, Any

COMPOUNDERS: Dict[str, Dict[str, Any]] = {
    "BAJFINANCE": {
        "start_date": "2014-01-01",
        "compounder_window": "2014-2021",
        "cagr": 35.4,
        "category": "Financial Compounder",
        "reason": "CAGR > 25% 10-year compounder"
    },
    "ASIANPAINT": {
        "start_date": "2010-01-01",
        "compounder_window": "2010-2020",
        "cagr": 22.1,
        "category": "Consumer Compounder",
        "reason": "Consistent high ROCE and market dominance"
    },
    "PIIND": {
        "start_date": "2013-01-01",
        "compounder_window": "2013-2020",
        "cagr": 38.2,
        "category": "Industrial Compounder",
        "reason": "CSM scale-up and margin expansion"
    },
    "ASTRAL": {
        "start_date": "2014-01-01",
        "compounder_window": "2014-2021",
        "cagr": 42.1,
        "category": "Industrial Compounder",
        "reason": "Brand moat in pipes, high growth"
    },
    "POLYCAB": {
        "start_date": "2019-04-01",
        "compounder_window": "2019-2024",
        "cagr": 45.0,
        "category": "Industrial Compounder",
        "reason": "Market share gains in FMEG"
    },
    "APLAPOLLO": {
        "start_date": "2015-01-01",
        "compounder_window": "2015-2023",
        "cagr": 39.5,
        "category": "Industrial Compounder",
        "reason": "Structural shift to structural steel"
    }
}

def get_compounders() -> Dict[str, Dict[str, Any]]:
    return COMPOUNDERS

def is_compounder_in_window(ticker: str, check_date: str) -> bool:
    """Check if the ticker is considered a compounder on the given date (YYYY-MM-DD format)."""
    if ticker not in COMPOUNDERS:
        return False
        
    c = COMPOUNDERS[ticker]
    # We parse out the year from check_date and compare against compounder_window
    try:
        check_year = int(check_date.split("-")[0])
        start_year, end_year = map(int, c["compounder_window"].split("-"))
        return start_year <= check_year <= end_year
    except Exception:
        return False
