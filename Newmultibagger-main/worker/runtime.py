from __future__ import annotations

import argparse
import asyncio

from modules.dependencies import (
    _json_safe_clean,
    _run_blocking,
    _run_sqlite_write_with_retry,
    _run_sqlite_write_with_retry_sync,
    _run_ticker_blocking,
    get_connection,
    manager,
)
from modules.structured_logger import SovereignLogger
from worker.background_jobs import run_price_update_loop, start_weekly_audit_thread

logger = SovereignLogger("sovereign.runtime.worker")


async def run_runtime_worker(*, skip_audit: bool = False) -> None:
    if not skip_audit:
        start_weekly_audit_thread(
            get_connection=get_connection,
            run_sqlite_write_with_retry_sync=_run_sqlite_write_with_retry_sync,
            logger=logger,
        )

    await run_price_update_loop(
        get_connection=get_connection,
        run_blocking=_run_blocking,
        run_ticker_blocking=_run_ticker_blocking,
        run_sqlite_write_with_retry=_run_sqlite_write_with_retry,
        broadcast_updates=manager.broadcast,
        json_cleaner=_json_safe_clean,
        logger=logger,
        startup_delay_seconds=0,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run background runtime jobs outside the web app process."
    )
    parser.add_argument(
        "--skip-audit",
        action="store_true",
        help="Run the price updater only.",
    )
    args = parser.parse_args()

    logger.info(
        "Starting standalone runtime worker",
        skip_audit=args.skip_audit,
    )
    asyncio.run(run_runtime_worker(skip_audit=args.skip_audit))


if __name__ == "__main__":
    main()
