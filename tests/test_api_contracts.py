from datetime import date
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import main
import modules.data_manager as data_manager_module
from app_routes import public as public_routes


def test_openapi_exposes_public_response_models():
    with TestClient(main.app) as client:
        spec = client.get("/openapi.json").json()

    health_schema = spec["paths"]["/api/health"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    news_schema = spec["paths"]["/api/news/{symbol}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    report_schema = spec["paths"]["/api/reports/{symbol}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    performance_schema = spec["paths"]["/api/performance"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    regime_schema = spec["paths"]["/api/regime_status"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]

    assert health_schema["$ref"].endswith("/HealthResponse")
    assert news_schema["$ref"].endswith("/NewsSignalResponse")
    assert report_schema["$ref"].endswith("/MarkdownReportResponse")
    assert performance_schema["$ref"].endswith("/PerformanceResponse")
    assert regime_schema["$ref"].endswith("/RegimeStatusResponse")


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
