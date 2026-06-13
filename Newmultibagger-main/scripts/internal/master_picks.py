# master_picks.py
# Consolidated list of all stocks provided by User

import os
import sys

# Add root directory to python path so we can import from ticker_list
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from ticker_list import TICKERS

MASTER_PICKS = TICKERS.copy()
# Remove TATAMOTORS.NS if it's giving 404
if "TATAMOTORS.NS" in MASTER_PICKS:
    MASTER_PICKS.remove("TATAMOTORS.NS")
    # Adding TATAMOTORS.BO as a fallback if needed, but for now just focus on the working ones.
