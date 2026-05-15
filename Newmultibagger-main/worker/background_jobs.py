from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff
from modules.runtime_settings import runtime_settings
from modules.structured_logger import SovereignLogger

AsyncCallable = Callable[..., Awaitable[Any]]
OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
SWING_FRESHNESS_DAYS = 2


def _coerce_symbol_list(symbols: Any) -> list[str]:
    if isinstance(symbols, str):
        return [symbols]
    return [str(symbol) for symbol in symbols]


def _extract_symbol_frame(
    download_frame: pd.DataFrame,
    batch: list[str],
    symbol: str,
) -> pd.DataFrame:
    if download_frame.empty:
        return pd.DataFrame()

    if isinstance(download_frame.columns, pd.MultiIndex):
        first_level = set(download_frame.columns.get_level_values(0))
        second_level = set(download_frame.columns.get_level_values(1))

        if symbol in first_level:
            symbol_frame = download_frame[symbol].copy()
        elif symbol in second_level:
            columns = {}
            for column in OHLCV_COLUMNS:
                key = (column, symbol)
                if key in download_frame.columns:
                    columns[column] = download_frame[key]
            symbol_frame = pd.DataFrame(columns)
        elif len(batch) == 1:
            symbol_frame = download_frame.droplevel(1, axis=1).copy()
        else:
            return pd.DataFrame()
    else:
        symbol_frame = download_frame.copy()

    symbol_frame = symbol_frame[[c for c in OHLCV_COLUMNS if c in symbol_frame.columns]]
    for column in symbol_frame.columns:
        symbol_frame[column] = pd.to_numeric(symbol_frame[column], errors="coerce")
    return symbol_frame.dropna(how="all")


def _latest_close_and_date(frame: pd.DataFrame) -> tuple[float | None, str | None]:
    if "Close" not in frame:
        return None, None

    close = frame["Close"].dropna()
    if close.empty:
        return None, None

    current_price = float(close.iloc[-1])
    latest_index = close.index[-1]
    latest_date = pd.Timestamp(latest_index).date().isoformat()
    return current_price, latest_date


def _extract_current_price(
    download_frame: pd.DataFrame,
    batch: list[str],
    symbol: str,
) -> float | None:
    current_price, _latest_date = _latest_close_and_date(
        _extract_symbol_frame(download_frame, batch, symbol)
    )
    return current_price


def _as_trade_date(value: Any) -> date | None:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return pd.Timestamp(parsed).date()


def _needs_tactical_refresh(row: dict[str, Any], *, today: date | None = None) -> bool:
    today = today or datetime.now().date()
    source_date = _as_trade_date(row.get("as_of_date") or row.get("updated_at"))
    if source_date is None:
        return True
    return (today - source_date).days > SWING_FRESHNESS_DAYS


def _safe_pct_return(close: pd.Series, periods: int) -> float:
    if len(close) <= periods:
        return 0.0
    start = close.iloc[-periods - 1]
    end = close.iloc[-1]
    if not pd.notna(start) or not pd.notna(end) or float(start) <= 0:
        return 0.0
    return round(float(end / start - 1), 4)


def _calculate_atr(frame: pd.DataFrame, window: int = 14) -> float:
    if not {"High", "Low", "Close"}.issubset(frame.columns):
        return 0.0

    high = frame["High"]
    low = frame["Low"]
    close = frame["Close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.dropna().tail(window).mean()
    if pd.isna(atr):
        return 0.0
    return round(float(atr), 2)


def _build_tactical_refresh_fields(
    history_frame: pd.DataFrame,
    *,
    current_price: float | None = None,
    price_as_of_date: str | None = None,
    refreshed_at: datetime | None = None,
) -> dict[str, Any] | None:
    if history_frame.empty or "Close" not in history_frame:
        return None

    close = history_frame["Close"].dropna()
    if close.empty:
        return None

    daily_price, daily_as_of_date = _latest_close_and_date(history_frame)
    price = current_price or daily_price
    if price is None or price <= 0:
        return None

    as_of_date = price_as_of_date or daily_as_of_date or datetime.now().date().isoformat()
    refreshed_at = refreshed_at or datetime.now()

    high_52w = float(history_frame["High"].dropna().tail(252).max()) if "High" in history_frame else price
    low_52w = float(history_frame["Low"].dropna().tail(252).min()) if "Low" in history_frame else price
    if not pd.notna(high_52w) or high_52w <= 0:
        high_52w = price
    if not pd.notna(low_52w) or low_52w <= 0:
        low_52w = price

    dist_from_52w_high = max((high_52w - price) / high_52w, 0.0)
    atr = _calculate_atr(history_frame)
    if atr <= 0:
        atr = round(price * 0.03, 2)

    volume_breakout = 1.0
    if "Volume" in history_frame:
        volume = history_frame["Volume"].dropna()
        avg_volume = volume.tail(20).mean()
        latest_volume = volume.iloc[-1] if not volume.empty else None
        if latest_volume is not None and pd.notna(avg_volume) and avg_volume > 0:
            volume_breakout = round(float(latest_volume / avg_volume), 2)

    return {
        "price": round(price, 2),
        "ret_1m": _safe_pct_return(close, 21),
        "ret_3m": _safe_pct_return(close, 63),
        "ret_6m": _safe_pct_return(close, 126),
        "vol_breakout": volume_breakout,
        "dist_from_52w_high": round(dist_from_52w_high, 4),
        "down_from_52w": round(dist_from_52w_high * 100, 2),
        "high_52w": round(high_52w, 2),
        "low_52w": round(low_52w, 2),
        "atr": atr,
        "stop_loss_atr": round(max(price - (2 * atr), price * 0.75), 2),
        "target_1": round(price + max(3 * atr, price * 0.08), 2),
        "as_of_date": as_of_date,
        "updated_at": refreshed_at.strftime("%Y-%m-%d %H:%M:%S"),
    }


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
    history_downloader: Callable[..., Any] | None = None,
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
    tactical_downloader = history_downloader or price_downloader

    if startup_delay > 0:
        await asyncio.sleep(startup_delay)

    while True:
        try:
            job_logger.info(
                "Starting background price refresh cycle",
                batch_size=batch_limit,
            )

            def _load_symbol_rows():
                conn = get_connection()
                try:
                    try:
                        df_local = pd.read_sql(
                            "SELECT symbol, as_of_date, updated_at FROM multibaggers",
                            conn,
                        )
                    except Exception:
                        df_local = pd.read_sql("SELECT symbol FROM multibaggers", conn)
                    return df_local.to_dict(orient="records")
                finally:
                    conn.close()

            symbol_rows = await run_blocking(_load_symbol_rows)
            all_symbols = [str(row["symbol"]) for row in symbol_rows if row.get("symbol")]
            stale_tactical_symbols = {
                str(row["symbol"]) for row in symbol_rows if row.get("symbol") and _needs_tactical_refresh(row)
            }
            if all_symbols:
                total_batches = (len(all_symbols) + batch_limit - 1) // batch_limit
                for index in range(0, len(all_symbols), batch_limit):
                    batch = all_symbols[index : index + batch_limit]
                    stale_batch = [symbol for symbol in batch if symbol in stale_tactical_symbols]
                    batch_no = index // batch_limit + 1
                    job_logger.info(
                        "Processing background price batch",
                        batch_index=batch_no,
                        total_batches=total_batches,
                        symbols=len(batch),
                    )

                    data = pd.DataFrame()
                    price_snapshots: dict[str, tuple[float, str | None]] = {}
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
                        for symbol in batch:
                            current_price, price_date = _latest_close_and_date(
                                _extract_symbol_frame(data, batch, symbol)
                            )
                            if current_price is not None:
                                price_snapshots[symbol] = (current_price, price_date)

                    updated_count = 0
                    if not data.empty:

                        def _write_batch_prices(b=batch, d=data, snapshots=price_snapshots):
                            conn = get_connection()
                            try:
                                cursor = conn.cursor()
                                updated = 0
                                for symbol in b:
                                    try:
                                        snapshot = snapshots.get(symbol)
                                        current_price = (
                                            snapshot[0]
                                            if snapshot is not None
                                            else _extract_current_price(d, b, symbol)
                                        )
                                        if current_price is None:
                                            continue
                                        cursor.execute(
                                            "UPDATE multibaggers SET price = ?, updated_at = ? WHERE symbol = ?",
                                            (
                                                round(float(current_price), 2),
                                                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                symbol,
                                            ),
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

                    tactical_updated_count = 0
                    if stale_batch:
                        history_data = pd.DataFrame()
                        try:
                            history_data = await run_with_exponential_backoff(
                                lambda b=stale_batch: run_ticker_blocking(
                                    tactical_downloader,
                                    b,
                                    period="1y",
                                    interval="1d",
                                    progress=False,
                                    auto_adjust=True,
                                    timeout=30,
                                ),
                                context=f"yfinance tactical batch {batch_no}",
                            )
                        except Exception as exc:
                            job_logger.warning(
                                "Tactical multibagger refresh download failed",
                                batch_index=batch_no,
                                error=str(exc),
                            )

                        if not history_data.empty:

                            def _write_tactical_fields(
                                b=stale_batch,
                                d=history_data,
                                snapshots=price_snapshots,
                            ):
                                conn = get_connection()
                                try:
                                    cursor = conn.cursor()
                                    refreshed = 0
                                    for symbol in b:
                                        try:
                                            price_snapshot = snapshots.get(symbol)
                                            fields = _build_tactical_refresh_fields(
                                                _extract_symbol_frame(d, b, symbol),
                                                current_price=(
                                                    price_snapshot[0]
                                                    if price_snapshot is not None
                                                    else None
                                                ),
                                                price_as_of_date=(
                                                    price_snapshot[1]
                                                    if price_snapshot is not None
                                                    else None
                                                ),
                                            )
                                            if not fields:
                                                continue
                                            cursor.execute(
                                                """
                                                UPDATE multibaggers
                                                SET price = ?,
                                                    ret_1m = ?,
                                                    ret_3m = ?,
                                                    ret_6m = ?,
                                                    vol_breakout = ?,
                                                    dist_from_52w_high = ?,
                                                    down_from_52w = ?,
                                                    high_52w = ?,
                                                    low_52w = ?,
                                                    atr = ?,
                                                    stop_loss_atr = ?,
                                                    target_1 = ?,
                                                    as_of_date = ?,
                                                    updated_at = ?
                                                WHERE symbol = ?
                                                """,
                                                (
                                                    fields["price"],
                                                    fields["ret_1m"],
                                                    fields["ret_3m"],
                                                    fields["ret_6m"],
                                                    fields["vol_breakout"],
                                                    fields["dist_from_52w_high"],
                                                    fields["down_from_52w"],
                                                    fields["high_52w"],
                                                    fields["low_52w"],
                                                    fields["atr"],
                                                    fields["stop_loss_atr"],
                                                    fields["target_1"],
                                                    fields["as_of_date"],
                                                    fields["updated_at"],
                                                    symbol,
                                                ),
                                            )
                                            refreshed += 1
                                        except Exception:
                                            continue
                                    conn.commit()
                                    return refreshed
                                finally:
                                    conn.close()

                            tactical_updated_count = await run_sqlite_write_with_retry(
                                _write_tactical_fields,
                                f"tactical multibaggers batch {batch_no}",
                            )
                            if tactical_updated_count:
                                job_logger.info(
                                    "Refreshed tactical multibagger fields",
                                    batch_index=batch_no,
                                    symbols=tactical_updated_count,
                                )

                    if updated_count + tactical_updated_count > 0 and broadcast_updates and json_cleaner:
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
