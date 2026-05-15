import asyncio
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app_routes.stocks as stocks_route_module
import main
import modules.dependencies as deps
from modules.runtime_settings import load_runtime_settings
from worker.background_jobs import run_price_update_loop, run_weekly_audit_loop


def test_runtime_settings_loads_worker_flags(monkeypatch):
    monkeypatch.setenv("EMBED_PRICE_UPDATER_IN_WEB", "true")
    monkeypatch.setenv("EMBED_WEEKLY_AUDIT_IN_WEB", "yes")
    monkeypatch.setenv("PRICE_UPDATE_INTERVAL_SECONDS", "42")
    monkeypatch.setenv("BLOCKING_IO_CONCURRENCY", "16")

    settings = load_runtime_settings()

    assert settings.embed_price_updater_in_web is True
    assert settings.embed_weekly_audit_in_web is True
    assert settings.price_update_interval_seconds == 42
    assert settings.blocking_io_concurrency == 16


def test_lifespan_skips_embedded_price_updater_when_disabled(monkeypatch):
    called = False

    async def fake_update_prices_background():
        nonlocal called
        called = True

    import modules.dependencies as deps

    monkeypatch.setattr(
        deps.runtime_settings,
        "embed_price_updater_in_web",
        False,
        raising=False,
    )
    monkeypatch.setattr(deps, "update_prices_background", fake_update_prices_background)

    with TestClient(main.app):
        pass

    assert called is False


def test_main_loads_from_parent_cwd_and_stocks_endpoint_still_works(monkeypatch):
    monkeypatch.chdir(ROOT.parent)
    monkeypatch.setattr(stocks_route_module.deps, "_read_records", lambda _query: [])

    module_name = "main_outside_project_cwd"
    spec = importlib.util.spec_from_file_location(module_name, ROOT / "main.py")
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.WEB_UI_DIR.is_absolute()
    assert module.WEB_UI_DIR.exists()

    module.app.dependency_overrides[deps.get_api_key] = lambda: "test-api-key"
    with TestClient(module.app) as client:
        response = client.get("/api/stocks")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_weekly_audit_loop_marks_stale_rows_in_run_once_mode(tmp_path):
    db_path = tmp_path / "runtime_hardening.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE multibaggers (
                symbol TEXT PRIMARY KEY,
                last_audited TEXT
            )
            """
        )
        conn.execute("INSERT INTO multibaggers VALUES ('AAA.NS', NULL)")
        conn.commit()
    finally:
        conn.close()

    def get_connection():
        return sqlite3.connect(db_path)

    def run_sync(write_fn, _operation_name):
        return write_fn()

    run_weekly_audit_loop(
        get_connection=get_connection,
        run_sqlite_write_with_retry_sync=run_sync,
        stale_after_days=7,
        poll_interval_seconds=0,
        run_once=True,
    )

    conn = sqlite3.connect(db_path)
    try:
        last_audited = conn.execute(
            "SELECT last_audited FROM multibaggers WHERE symbol = 'AAA.NS'"
        ).fetchone()[0]
    finally:
        conn.close()

    assert isinstance(last_audited, str)
    assert len(last_audited) >= 10


def test_price_update_loop_refreshes_swing_tactical_fields(tmp_path):
    db_path = tmp_path / "runtime_hardening.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE multibaggers (
                symbol TEXT PRIMARY KEY,
                price REAL,
                as_of_date TEXT,
                updated_at TEXT,
                ret_1m REAL,
                ret_3m REAL,
                ret_6m REAL,
                vol_breakout REAL,
                dist_from_52w_high REAL,
                down_from_52w REAL,
                high_52w REAL,
                low_52w REAL,
                atr REAL,
                stop_loss_atr REAL,
                target_1 REAL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO multibaggers (
                symbol, price, as_of_date, updated_at, ret_1m, ret_3m, ret_6m,
                vol_breakout, dist_from_52w_high, down_from_52w, high_52w,
                low_52w, atr, stop_loss_atr, target_1
            )
            VALUES ('AAA.NS', 100, '2026-05-01', '2026-05-01 10:00:00', 0, 0, 0, 1, 0, 0, 100, 80, 1, 95, 110)
            """
        )
        conn.commit()
    finally:
        conn.close()

    def fake_download(symbols, *, period, interval, **_kwargs):
        symbol_list = [symbols] if isinstance(symbols, str) else list(symbols)
        if interval == "1m":
            index = pd.date_range("2026-05-08 15:28:00", periods=2, freq="min")
            closes = [208.0, 210.0]
        else:
            index = pd.bdate_range(end="2026-05-08", periods=130)
            closes = [100.0 + i for i in range(len(index))]

        data = {}
        for symbol in symbol_list:
            data[("Open", symbol)] = [value - 1 for value in closes]
            data[("High", symbol)] = [value + 4 for value in closes]
            data[("Low", symbol)] = [value - 4 for value in closes]
            data[("Close", symbol)] = closes
            data[("Volume", symbol)] = [1000 + i for i in range(len(index))]

        return pd.DataFrame(data, index=index)

    def get_connection():
        return sqlite3.connect(db_path)

    async def run_blocking(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def run_ticker_blocking(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    async def run_write(write_fn, _operation_name):
        return write_fn()

    asyncio.run(
        run_price_update_loop(
            get_connection=get_connection,
            run_blocking=run_blocking,
            run_ticker_blocking=run_ticker_blocking,
            run_sqlite_write_with_retry=run_write,
            startup_delay_seconds=0,
            batch_size=1,
            batch_pause_seconds=0,
            price_downloader=fake_download,
            run_once=True,
        )
    )

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            """
            SELECT price, as_of_date, ret_1m, ret_3m, ret_6m, vol_breakout,
                   dist_from_52w_high, down_from_52w, high_52w, low_52w,
                   atr, stop_loss_atr, target_1
            FROM multibaggers WHERE symbol = 'AAA.NS'
            """
        ).fetchone()
    finally:
        conn.close()

    assert row[0] == 210.0
    assert row[1] == "2026-05-08"
    assert row[2] > 0
    assert row[3] > 0
    assert row[4] > 0
    assert row[5] > 0
    assert 0 <= row[6] <= 1
    assert row[7] >= 0
    assert row[8] >= row[0]
    assert row[9] <= row[0]
    assert row[10] > 0
    assert row[11] < row[0]
    assert row[12] > row[0]
