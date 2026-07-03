from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Skip DuckDB sqlite_scanner download in CI/sandboxed environments.
# Must be set before db.db_core is imported (which happens when main.py is imported).
import os as _os
_os.environ.setdefault("DUCKDB_SKIP_SQLITE_EXT", "1")
_os.environ.setdefault("SOVEREIGN_TESTING", "1")  # skip lifespan background tasks (ML bootstrap, pub/sub, webhook retry)


ROOT = Path(__file__).resolve().parents[1]


def _load_real_module(module_name: str, relative_path: str):
    module_path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"Unable to load module {module_name} from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[module_name] = module
    return module


def pytest_runtest_setup(item):
    """
    Prevent global MagicMock stubs from other test modules from leaking into
    ``test_new_features`` during full-suite execution.
    """
    if item.module.__name__.endswith("test_new_features"):
        estimates = _load_real_module("modules.estimates", "modules/estimates.py")
        promoter_intel = _load_real_module("modules.promoter_intel", "modules/intelligence/promoter_intel.py")

        item.module.analyze_estimate_momentum = estimates.analyze_estimate_momentum
        item.module.compute_own_estimate = estimates.compute_own_estimate
        item.module.calculate_promoter_score = promoter_intel.calculate_promoter_score


@pytest.fixture(autouse=True)
def bypass_api_key_dependency_for_route_tests(request):
    """
    Most route tests exercise endpoint behavior, not authentication. Keep the
    dedicated auth test on the real dependency and bypass the global app guard
    elsewhere so local .env values do not make the suite order-dependent.
    """
    if request.node.name == "test_global_api_key_enforcement":
        yield
        return

    try:
        import main
        import modules.dependencies as deps
    except Exception:
        yield
        return

    # Override both dependency locations — auth was refactored but both
    # paths must be patched to handle direct and global app-level deps.
    import modules.auth as _auth
    main.app.dependency_overrides[deps.get_api_key]  = lambda: "test-api-key"
    main.app.dependency_overrides[_auth.get_api_key] = lambda: "test-api-key"
    try:
        yield
    finally:
        main.app.dependency_overrides.pop(deps.get_api_key,  None)
        main.app.dependency_overrides.pop(_auth.get_api_key, None)


@pytest.fixture(autouse=True)
def patch_duckdb_for_tests(monkeypatch):
    """Prevent DuckDB sqlite_scanner download and reset the connection per test.

    Resetting _duck_local between tests prevents stale in-memory schema from
    one test leaking into the next (isolation fix for test_price_fundamentals_api,
    test_regime_api, test_runtime_hardening order-sensitivity failures).
    """
    try:
        import duckdb
        import db.db_core as _db_core

        # Reset any leftover connection from a prior test
        _db_core._duck_local.conn = None

        def _safe_duckdb():
            conn = getattr(_db_core._duck_local, "conn", None)
            if conn is not None:
                try:
                    conn.execute("SELECT 1").fetchone()
                    return conn
                except Exception:
                    pass
            conn = duckdb.connect(":memory:")
            _db_core._duck_local.conn = conn
            return conn

        monkeypatch.setattr(_db_core, "get_duckdb_connection", _safe_duckdb)
    except Exception:
        pass
    yield
    # Tear down: close the per-test DuckDB connection
    try:
        import db.db_core as _db_core
        conn = getattr(_db_core._duck_local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        _db_core._duck_local.conn = None
    except Exception:
        pass
