import os
from datetime import datetime

import pandas as pd
from modules.structured_logger import SovereignLogger, format_log_message
_log = SovereignLogger("modules.tracking.alpha_tracker").logger

LOG_FILE = "alpha_log.csv"


def track_alpha(strategy_cagr, benchmark_cagr, alpha):
    """
    Phase 24: Alpha Decay Tracker.
    Logs the performance of the strategy and checks for decay.
    """
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    new_row = {
        "Date": date_str,
        "Strategy_CAGR": round(strategy_cagr * 100, 2),
        "Benchmark_CAGR": round(benchmark_cagr * 100, 2),
        "Alpha": round(alpha * 100, 2),
    }

    # 1. Load or Create Log
    if os.path.exists(LOG_FILE):
        df = pd.read_csv(LOG_FILE)
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    else:
        df = pd.DataFrame([new_row])

    # Save
    df.to_csv(LOG_FILE, index=False)

    _log.info(format_log_message("\n" + "=" * 40))
    _log.info(format_log_message("📉 PHASE 24: ALPHA DECAY TRACKER"))
    _log.info(format_log_message("=" * 40))
    _log.info(format_log_message(f"Logged Performance: Alpha {new_row['Alpha']}%"))

    # 2. Analyze Decay (Last 5 runs)
    if len(df) >= 3:
        recent = df.tail(3)
        alphas = recent["Alpha"].tolist()

        # Check if strictly decreasing
        if alphas[0] > alphas[1] > alphas[2]:
            _log.warning(format_log_message("⚠️  WARNING: ALPHA DECAY DETECTED!"))
            _log.info(format_log_message(f"    Trend: {alphas[0]}% -> {alphas[1]}% -> {alphas[2]}%"))
            _log.info(format_log_message("    Suggestion: Trigger Factor Review (Phase 24)"))
        else:
            _log.info(format_log_message("✅  Alpha Stability: Healthy"))

    _log.info(format_log_message("=" * 40 + "\n"))
