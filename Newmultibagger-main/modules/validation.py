import datetime

from modules.backtest import run_performance_analysis
from modules.structured_logger import SovereignLogger, format_log_message
_log = SovereignLogger("modules.validation").logger

logger = SovereignLogger("sovereign.validation")


def validate_robustness(tickers):
    """
    Phase 31: Walk-Forward Robustness Check (Multi-Regime Testing).
    Tests the selected portfolio across different market years to check consistency.

    Since we cannot 're-screen' historical universes without a PIT database,
    we validate the *durability* of the current selection.
    """
    _log.info(format_log_message("\n" + "=" * 50))
    _log.info(format_log_message("🔬 PHASE 31: WALK-FORWARD ROBUSTNESS CHECK"))
    _log.info(format_log_message("   (Testing Portfolio Durability Across Market Cycles)"))
    _log.info(format_log_message("=" * 50))

    # Define Cycles
    cycles = [
        {"name": "2022 (Bear/Volatile)", "start": "2022-01-01", "end": "2022-12-31"},
        {"name": "2023 (Recovery)", "start": "2023-01-01", "end": "2023-12-31"},
        {
            "name": "2024-Present (Bull)",
            "start": "2024-01-01",
            "end": datetime.datetime.now().strftime("%Y-%m-%d"),
        },
    ]

    scorecard = []

    for cycle in cycles:
        _log.info(format_log_message(f"\n--- Testing Regime: {cycle['name']} ---"))
        try:
            # We use Equal Weight for robustness check to see if the 'Picks' are good
            # (ignoring dynamic weights for history)
            res = run_performance_analysis(
                tickers, weights=None, start_date=cycle["start"], end_date=cycle["end"]
            )

            if res:
                alpha = res.get("Alpha", 0)
                status = "PASS ✅" if alpha > 0 else "FAIL ❌"
                scorecard.append(f"{cycle['name']:<20} | Alpha: {alpha:>6.1f}% | {status}")
            else:
                scorecard.append(f"{cycle['name']:<20} | NO DATA")

        except Exception as e:
            logger.exception(f"Error in {cycle['name']} robustness check", exc_info=e)
            _log.error(format_log_message(f"Error in {cycle['name']}: {e}"))

    _log.info(format_log_message("\n" + "-" * 50))
    _log.info(format_log_message("ROBUSTNESS SCORECARD"))
    _log.info(format_log_message("-" * 50))
    for line in scorecard:
        _log.info(format_log_message(line))

    _log.info(format_log_message("-" * 50))
    # Final Verdict
    pass_count = sum(1 for line in scorecard if "PASS" in line)
    if pass_count == 3:
        _log.info(format_log_message("🏆 VERDICT: INSTITUTIONAL GRADE (All-Weather Alpha)"))
    elif pass_count == 2:
        _log.info(format_log_message("🥈 VERDICT: ROBUST (Survives most regimes)"))
    else:
        _log.warning(format_log_message("⚠️ VERDICT: FRAGILE (Regime Dependent)"))
    _log.info(format_log_message("=" * 50 + "\n"))
