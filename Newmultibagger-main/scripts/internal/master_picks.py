# master_picks.py
# Consolidated list of all stocks provided by User

import os
import sys

# Add root directory to python path so we can import from ticker_list
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
import modules.adapters.yf_patch  # noqa: F401

from ticker_list import TICKERS

MASTER_PICKS = TICKERS.copy()
# Remove TATAMOTORS.NS and AKZOINDIA.NS if they give 404 and hang
if "TATAMOTORS.NS" in MASTER_PICKS:
    MASTER_PICKS.remove("TATAMOTORS.NS")
if "AKZOINDIA.NS" in MASTER_PICKS:
    MASTER_PICKS.remove("AKZOINDIA.NS")
    # Adding TATAMOTORS.BO as a fallback if needed, but for now just focus on the working ones.
