import sys
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main
import modules.data_service as data_manager_module
from app_routes import public as public_routes


def test_openapi_exposes_15_core_endpoints():
    """Phase 4.3: Add contract regression tests for all 15 API endpoints."""
    with TestClient(main.app) as client:
        spec = client.get("/openapi.json").json()

    core_endpoints = [
        "/api/health",
        "/api/health/deep",
        "/api/swarm/status/{symbol}",
        "/api/swarm/report/{symbol}",
        "/api/news/{symbol}",
        "/api/market-calendar",
        "/api/reports/{symbol}",
        "/api/performance",
        "/api/regime_status",
        "/api/stocks",
        "/api/multibagger-hunt",
        "/api/history/{symbol}",
        "/api/valuation/{symbol}",
        "/api/financials/{symbol}",
        "/api/data-freshness",
    ]

    paths = spec.get("paths", {})

    for endpoint in core_endpoints:
        assert endpoint in paths, f"Endpoint {endpoint} missing from OpenAPI spec"

        # Verify it has a GET method and a 200 response
        methods = paths[endpoint]
        assert "get" in methods, f"Endpoint {endpoint} missing GET method"

        responses = methods["get"].get("responses", {})
        assert "200" in responses, f"Endpoint {endpoint} missing 200 response contract"

        # Verify the 200 response has application/json content schema
        content = responses["200"].get("content", {})
        if "application/json" in content:
            schema = content["application/json"].get("schema")
            assert schema is not None, f"Endpoint {endpoint} missing response schema"


def test_news_endpoint_contract(monkeypatch):
    monkeypatch.setattr(
        public_routes.news_engine,
        "get_alpha_signal",
        lambda symbol: {
            "symbol": symbol,
            "sentiment_score": 0.35,
            "alignment": "Positive Drift",
            "headline_count": 2,
            "headlines": ["Headline 1", "Headline 2"],
        },
    )

    with TestClient(main.app) as client:
        response = client.get("/api/news/INFY.NS")

    assert response.status_code == 200
    assert response.json() == {
        "symbol": "INFY.NS",
        "sentiment_score": 0.35,
        "alignment": "Positive Drift",
        "headline_count": 2,
        "headlines": ["Headline 1", "Headline 2"],
    }


def test_market_calendar_serializes_dates(monkeypatch):
    monkeypatch.setattr(
        data_manager_module.data_manager,
        "valid_trading_days",
        [date(2026, 4, 3), date(2026, 4, 6)],
    )

    with TestClient(main.app) as client:
        response = client.get("/api/market-calendar")

    assert response.status_code == 200
    assert response.json() == {"valid_trading_days": ["2026-04-03", "2026-04-06"]}
