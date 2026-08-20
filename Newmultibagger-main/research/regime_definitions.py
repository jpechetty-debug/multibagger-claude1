"""
research/regime_definitions.py

Centrally defines market regimes used in validation and scoring.
Provides logic to classify a given date or period into a specific regime.
"""

from enum import Enum
from typing import Dict, Any

class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"

# In a live system, this might use the HMM classifier or historical index data.
# For historical validation, we can approximate regimes by known periods in the Indian market
# or use a simplified rule-based system if an HMM isn't loaded.

HISTORICAL_REGIMES = [
    {"start": "2010-01-01", "end": "2010-12-31", "regime": MarketRegime.BULL},
    {"start": "2011-01-01", "end": "2011-12-31", "regime": MarketRegime.BEAR},
    {"start": "2012-01-01", "end": "2013-12-31", "regime": MarketRegime.RANGE},
    {"start": "2014-01-01", "end": "2015-02-28", "regime": MarketRegime.BULL},
    {"start": "2015-03-01", "end": "2016-02-28", "regime": MarketRegime.BEAR},
    {"start": "2016-03-01", "end": "2017-12-31", "regime": MarketRegime.BULL},
    {"start": "2018-01-01", "end": "2019-12-31", "regime": MarketRegime.RANGE},
    {"start": "2020-01-01", "end": "2020-05-31", "regime": MarketRegime.HIGH_VOLATILITY},
    {"start": "2020-06-01", "end": "2021-10-31", "regime": MarketRegime.BULL},
    {"start": "2021-11-01", "end": "2023-03-31", "regime": MarketRegime.RANGE},
    {"start": "2023-04-01", "end": "2024-12-31", "regime": MarketRegime.BULL},
]

def get_regime_for_date(check_date: str) -> str:
    """Returns the market regime for a given date (YYYY-MM-DD)."""
    for period in HISTORICAL_REGIMES:
        if period["start"] <= check_date <= period["end"]:
            return period["regime"].value
    return MarketRegime.RANGE.value
