import sys
from pathlib import Path

from fastapi.testclient import TestClient

# Add root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app

client = TestClient(app)


def test_api_v96_health():
    """Verify that /api/health is online and returns actual timestamp metadata."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert "latency_reference" in data


def test_api_v96_momentum_accel_sync():
    """Verify that /api/regime_status includes the momentum_accel field for terminal sync."""
    response = client.get("/api/regime_status")
    assert response.status_code == 200
    data = response.json()
    assert "regime" in data
    assert "details" in data
    assert "momentum_accel" in data
    # Acceleration should be a float
    assert isinstance(data["momentum_accel"], (int, float))
