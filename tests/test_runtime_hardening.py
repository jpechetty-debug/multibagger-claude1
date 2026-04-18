import importlib.util
import sqlite3
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main
import app_routes.stocks as stocks_route_module
from modules.runtime_settings import load_runtime_settings
from worker.background_jobs import run_weekly_audit_loop


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

    with TestClient(module.app) as client:
        response = client.get("/api/stocks")

    assert response.status_code == 200
    assert response.json() == []


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
