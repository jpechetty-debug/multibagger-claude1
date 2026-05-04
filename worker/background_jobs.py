from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff
from modules.runtime_settings import runtime_settings
from modules.structured_logger import SovereignLogger

AsyncCallable = Callable[..., Awaitable[Any]]


def _extract_current_price(
    download_frame: pd.DataFrame,
    batch: list[str],
    symbol: str,
) -> float | None:
    if "Close" not in download_frame:
        return None

    close_frame = download_frame["Close"]
    if len(batch) > 1:
        if hasattr(close_frame, "columns") and symbol in close_frame.columns:
            current_price = close_frame[symbol].iloc[-1]
        else:
            return None
    else:
        current_price = close_frame.iloc[-1]

    if pd.isna(current_price):
        return None
    return float(current_price)


async def run_price_update_loop(
    *,
    get_connection: Callable[[], Any],
    run_blocking: AsyncCallable,
    run_ticker_blocking: AsyncCallable,
    run_sqlite_write_with_retry: Callable[[Callable[[], Any], str], Awaitable[Any]],
    broadcast_updates: Callable[[dict[str, Any]], Awaitable[Any]] | None = None,
    json_cleaner: Callable[[Any], Any] | None = None,
    logger: SovereignLogger | None = None,
    startup_delay_seconds: int | None = None,
    batch_size: int | None = None,
    batch_pause_seconds: float | None = None,
    refresh_interval_seconds: int | None = None,
    price_downloader: Callable[..., Any] = yf.download,
    run_once: bool = False,
) -> None:
    job_logger = logger or SovereignLogger("sovereign.runtime.worker")
    startup_delay = (
        runtime_settings.price_update_startup_delay_seconds
        if startup_delay_seconds is None
        else startup_delay_seconds
    )
    batch_limit = runtime_settings.price_update_batch_size if batch_size is None else batch_size
    batch_pause = (
        runtime_settings.price_update_batch_pause_seconds
        if batch_pause_seconds is None
        else batch_pause_seconds
    )
    refresh_interval = (
        runtime_settings.price_update_interval_seconds
        if refresh_interval_seconds is None
        else refresh_interval_seconds
    )

    if startup_delay > 0:
        await asyncio.sleep(startup_delay)

    while True:
        try:
            job_logger.info(
                "Starting background price refresh cycle",
                batch_size=batch_limit,
            )

            def _load_symbols():
                conn = get_connection()
                try:
                    df_local = pd.read_sql("SELECT symbol FROM multibaggers", conn)
                    return df_local["symbol"].tolist()
                finally:
                    conn.close()

            all_symbols = await run_blocking(_load_symbols)
            if all_symbols:
                total_batches = (len(all_symbols) + batch_limit - 1) // batch_limit
                for index in range(0, len(all_symbols), batch_limit):
                    batch = all_symbols[index : index + batch_limit]
                    batch_no = index // batch_limit + 1
                    job_logger.info(
                        "Processing background price batch",
                        batch_index=batch_no,
                        total_batches=total_batches,
                        symbols=len(batch),
                    )

                    data = pd.DataFrame()
                    try:
                        data = await run_with_exponential_backoff(
                            lambda b=batch: run_ticker_blocking(
                                price_downloader,
                                b,
                                period="1d",
                                interval="1m",
                                progress=False,
                                auto_adjust=True,
                                timeout=15,
                            ),
                            context=f"yfinance background batch {batch_no}",
                        )
                    except Exception as exc:
                        job_logger.warning(
                            "Background price batch download failed",
                            batch_index=batch_no,
                            error=str(exc),
                        )

                    if not data.empty:

                        def _write_batch_prices(b=batch, d=data):
                            conn = get_connection()
                            try:
                                cursor = conn.cursor()
                                updated = 0
                                for symbol in b:
                                    try:
                                        current_price = _extract_current_price(
                                            d,
                                            b,
                                            symbol,
                                        )
                                        if current_price is None:
                                            continue
                                        cursor.execute(
                                            "UPDATE multibaggers SET price = ? WHERE symbol = ?",
                                            (current_price, symbol),
                                        )
                                        updated += 1
                                    except Exception:
                                        continue
                                conn.commit()
                                return updated
                            finally:
                                conn.close()

                        updated_count = await run_sqlite_write_with_retry(
                            _write_batch_prices,
                            f"background batch {batch_no}",
                        )
                        if updated_count > 0 and broadcast_updates and json_cleaner:
                            try:
                                placeholders = ",".join(["?"] * len(batch))
                                query = (
                                    f"SELECT * FROM multibaggers WHERE symbol IN ({placeholders})"
                                )

                                def _read_batch_records(q=query, b=batch):
                                    conn = get_connection()
                                    try:
                                        df = pd.read_sql(q, conn, params=b)
                                        return json.loads(
                                            df.to_json(
                                                orient="records",
                                                double_precision=2,
                                            )
                                        )
                                    finally:
                                        conn.close()

                                updated_records = await run_blocking(_read_batch_records)
                                await broadcast_updates(
                                    {
                                        "type": "update",
                                        "data": json_cleaner(updated_records),
                                    }
                                )
                            except Exception as exc:
                                job_logger.warning(
                                    "Failed to broadcast refreshed price batch",
                                    batch_index=batch_no,
                                    error=str(exc),
                                )

                    await asyncio.sleep(batch_pause)

            job_logger.info(
                "Completed background price refresh cycle",
                symbols=len(all_symbols),
            )
        except asyncio.CancelledError:
            job_logger.info("Background price updater cancelled")
            raise
        except Exception as exc:
            job_logger.error(
                "Background price updater loop failed",
                error=str(exc),
            )

        if run_once:
            return
        await asyncio.sleep(refresh_interval)


def run_weekly_audit_loop(
    *,
    get_connection: Callable[[], Any],
    run_sqlite_write_with_retry_sync: Callable[[Callable[[], Any], str], Any],
    logger: SovereignLogger | None = None,
    stale_after_days: int | None = None,
    poll_interval_seconds: int | None = None,
    stop_event: threading.Event | None = None,
    run_once: bool = False,
) -> None:
    job_logger = logger or SovereignLogger("sovereign.runtime.audit")
    stale_days = (
        runtime_settings.weekly_audit_stale_after_days
        if stale_after_days is None
        else stale_after_days
    )
    poll_seconds = (
        runtime_settings.weekly_audit_poll_interval_seconds
        if poll_interval_seconds is None
        else poll_interval_seconds
    )

    while True:
        try:
            job_logger.info(
                "Checking for stale forensic audits",
                stale_after_days=stale_days,
            )
            conn = get_connection()
            try:
                stale_cutoff = (datetime.now() - timedelta(days=stale_days)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
                query = (
                    "SELECT symbol FROM multibaggers "
                    "WHERE last_audited IS NULL OR last_audited < ? "
                    "LIMIT 5"
                )
                expired_stocks = pd.read_sql(query, conn, params=(stale_cutoff,))["symbol"].tolist()
            finally:
                conn.close()

            if expired_stocks:
                job_logger.info(
                    "Refreshing stale forensic audit markers",
                    symbols=",".join(expired_stocks),
                )
                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                def _write_audit_marks(expired=expired_stocks, t=now_str):
                    conn_write = get_connection()
                    try:
                        for symbol in expired:
                            conn_write.execute(
                                "UPDATE multibaggers SET last_audited = ? WHERE symbol = ?",
                                (t, symbol),
                            )
                        conn_write.commit()
                    finally:
                        conn_write.close()

                run_sqlite_write_with_retry_sync(
                    _write_audit_marks,
                    "weekly audit refresh",
                )
        except Exception as exc:
            job_logger.error("Weekly audit loop failed", error=str(exc))

        if run_once:
            return
        if stop_event and stop_event.wait(poll_seconds):
            job_logger.info("Weekly audit loop stopped by signal")
            return
        time.sleep(poll_seconds)


def start_weekly_audit_thread(
    *,
    get_connection: Callable[[], Any],
    run_sqlite_write_with_retry_sync: Callable[[Callable[[], Any], str], Any],
    logger: SovereignLogger | None = None,
) -> threading.Thread:
    job_logger = logger or SovereignLogger("sovereign.runtime.audit")
    thread = threading.Thread(
        target=run_weekly_audit_loop,
        kwargs={
            "get_connection": get_connection,
            "run_sqlite_write_with_retry_sync": run_sqlite_write_with_retry_sync,
            "logger": job_logger,
        },
        daemon=True,
        name="weekly-audit-loop",
    )
    thread.start()
    job_logger.info("Started weekly audit thread")
    return thread
