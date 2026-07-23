import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from main import app  # noqa: E402


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_read_root(client):
    response = client.get("/")
    assert response.status_code == 200


def test_get_stocks(client):
    response = client.get("/api/stocks")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_microcaps(client):
    response = client.get("/api/microcaps")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

