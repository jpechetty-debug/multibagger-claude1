import pytest

from modules.data_layer import intel_cache


@pytest.fixture(autouse=True)
def _tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(intel_cache, "CACHE_PATH", tmp_path / "intel.db")
    monkeypatch.delenv("INTEL_CACHE_DISABLED", raising=False)


def test_second_call_same_day_is_served_from_cache():
    calls = []

    @intel_cache.daily_cached("t")
    def lookup(symbol):
        calls.append(symbol)
        return {"v": len(calls)}

    assert lookup("A") == lookup("A") == {"v": 1}
    assert calls == ["A"]
    assert lookup("B") == {"v": 2}


def test_failure_is_cached_so_timeouts_are_not_retried():
    calls = []

    @intel_cache.daily_cached("t")
    def lookup(symbol):
        calls.append(symbol)
        raise TimeoutError("nse")

    for _ in range(3):
        with pytest.raises(Exception):
            lookup("A")
    assert calls == ["A"]


def test_disable_switch_bypasses_cache(monkeypatch):
    monkeypatch.setenv("INTEL_CACHE_DISABLED", "true")
    calls = []

    @intel_cache.daily_cached("t")
    def lookup(symbol):
        calls.append(symbol)
        return 1

    lookup("A")
    lookup("A")
    assert calls == ["A", "A"]
