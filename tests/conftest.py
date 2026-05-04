from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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
        promoter_intel = _load_real_module("modules.promoter_intel", "modules/promoter_intel.py")

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

    main.app.dependency_overrides[deps.get_api_key] = lambda: "test-api-key"
    try:
        yield
    finally:
        main.app.dependency_overrides.pop(deps.get_api_key, None)
