from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config
import main
import modules.data_service as market_data_module
import modules.dependencies as deps


def test_regime_status_normalizes_provider_payload(monkeypatch):
    original_forced_regime = config.FORCED_REGIME

    class FakeMarketDataProvider:
        def get_market_regime(self):
            return {
                "regime": "VOLATILE",
                "strategy_suggestion": "value",
                "details": {
                    "vix": 18.2,
                    "vix_threshold": 16.8,
                    "momentum_accel": 1.25,
                },
                "votes": {"BULL": 1, "BEAR": 1, "SIDEWAYS": 2},
            }

    monkeypatch.setattr(market_data_module, "MarketDataProvider", FakeMarketDataProvider)

    try:
        config.FORCED_REGIME = None
        deps._cache_invalidate(deps.regime_cache)
        with TestClient(main.app) as client:
            response = client.get("/api/regime_status")

        payload = response.json()
        assert response.status_code == 200
        assert payload["regime"] == "SIDEWAYS"
        assert payload["vix"] == 18.2
        assert payload["vix_threshold"] == 16.8
        assert payload["momentum_accel"] == 1.25
        assert payload["is_forced"] is False
        assert payload["stale"] is False
        assert payload["error"] is None
        assert payload["details"]["detected_regime"] == "SIDEWAYS"
    finally:
        config.FORCED_REGIME = original_forced_regime
        deps._cache_invalidate(deps.regime_cache)


def test_force_regime_accepts_labels_and_auto_reset():
    original_forced_regime = config.FORCED_REGIME

    try:
        deps._cache_invalidate(deps.regime_cache)
        with TestClient(main.app) as client:
            force = client.post("/api/admin/force_regime?regime=BULL")
            reset = client.post("/api/admin/force_regime?regime=AUTO")

        assert force.status_code == 200
        assert force.json() == {"status": "success", "regime": "BULL"}
        assert reset.status_code == 200
        assert reset.json() == {"status": "success", "regime": "AUTO"}
        assert config.FORCED_REGIME is None
    finally:
        config.FORCED_REGIME = original_forced_regime
        deps._cache_invalidate(deps.regime_cache)
