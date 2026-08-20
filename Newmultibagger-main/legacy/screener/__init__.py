"""
Screener sub-package.

Modularized from the monolithic scripts/internal/screener.py (~96KB).
Each module handles a specific concern of the screening pipeline.
"""

from modules.screener.quality import calculate_data_quality
from modules.screener.universe import load_universe_flags, save_universe_flags
from modules.screener.momentum import analyze_market_regime

__all__ = [
    "calculate_data_quality",
    "load_universe_flags",
    "save_universe_flags",
    "analyze_market_regime",
]
