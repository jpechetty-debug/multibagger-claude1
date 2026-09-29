from datetime import date

import pytest

from research import super_investor_registry as registry

pytestmark = pytest.mark.unit


def test_registry_uses_quarter_end_for_staleness():
    assert registry._registry_quarter_end("2026-Q2") == date(2026, 6, 30)


def test_refreshed_registry_contains_latest_disclosed_holdings():
    assert registry.REGISTRY_AS_OF == "2026-Q2"
    assert registry.get_super_investor_interest("CHENNPETRO") == ["DOLLY_KHANNA"]
    assert "ASHISH_KACHOLIA" in registry.get_super_investor_interest("SHAILY.NS")
