"""
Download missing NSE bhavcopy trading days into runtime/bhavcopy_history/.

First run seeds ~13 months (a few minutes); later runs fetch only new days.

Usage:
    python scripts/internal/update_bhavcopy_history.py            # last 400 days
    python scripts/internal/update_bhavcopy_history.py --days 800 # for 2y windows
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules.adapters.bhavcopy_history import HISTORY_DIR, update_cache  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=400, help="calendar days to cover (default 400)")
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    logging.disable(logging.WARNING)
    started = time.monotonic()
    stats = update_cache(days=args.days, workers=args.workers)
    files = len(list(HISTORY_DIR.glob("eq_*.csv")))
    print(f"{stats} | cached trading days: {files} | {time.monotonic() - started:.0f}s")
    return 1 if stats["error"] else 0


if __name__ == "__main__":
    sys.exit(main())
