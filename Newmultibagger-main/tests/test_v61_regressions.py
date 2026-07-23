import os
import sys
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from modules.scoring.engine import calculate_institutional_score
from modules.scoring.factors import _resolve_mode_and_weights


def test_pledge_penalty():
    """Verify that pledge > 0 correctly penalises the conviction score."""
    base_data = {
        "symbol": "TEST.NS",
        "Market_Cap_Cr": 1000,
        "Sales_Growth_5Y%": 20,
        "Avg_ROE_5Y%": 20,
        "F_Score": 6,
        "Debt_Equity": 0.5,
        "RS_Rating": 80,
        "ROE%": 20,
    }

    # Calculate with 30% pledge
    data_with_pledge = dict(base_data, Pledge_Pct=30)
    result_with_pledge = calculate_institutional_score(data_with_pledge)

    # Calculate with 0% pledge
    data_no_pledge = dict(base_data, Pledge_Pct=0)
    result_no_pledge = calculate_institutional_score(data_no_pledge)

    assert result_with_pledge["conviction_score"] < result_no_pledge["conviction_score"], "Pledge should penalise conviction score"

def test_bull_regime_uses_momentum_weights():
    """Verify that 'Bull Market' maps to momentum weight set."""
    _, weights, _ = _resolve_mode_and_weights("Bull Market")
    assert weights["w_mom"] > weights["w_val"], "Bull regime should heavily weigh momentum over value"

def test_multibagger_hunt_threshold():
    """Verify multibagger-hunt filters properly with >= 15 threshold."""
    client = TestClient(app)

    with patch("app_routes.stocks._duck_query", return_value=pd.DataFrame()) as mock_dq:
        response = client.get("/api/multibagger-hunt")
        assert response.status_code == 200

        mock_dq.assert_called_once()
        query = mock_dq.call_args[0][0]

        assert "CAST(sales_cagr_5y AS DOUBLE) >= 15" in query, "sales_cagr_5y threshold should be >= 15"
        assert "CAST(avg_roe_5y AS DOUBLE) >= 15" in query, "avg_roe_5y threshold should be >= 15"
        assert "CAST(score AS DOUBLE) >= 70.0" in query
        assert "data_confidence" in query
        assert "stale_data" in query


def test_multibagger_hunt_applies_phase1_trust_gate():
    client = TestClient(app)
    base = {
        "price": 100.0,
        "sector": "Tech",
        "score": 82.0,
        "f_score": 7,
        "rating": "A",
        "sales_cagr_5y": 22.0,
        "avg_roe_5y": 21.0,
        "debt_equity": 0.2,
        "cfo_pat_ratio": 1.1,
        "promoter_holding": 55.0,
        "pledge_pct": 0.0,
        "piotroski_score": 7,
        "market_cap_cr": 2500.0,
        "data_confidence": 75.0,
        "data_quality_flags": "",
        "avg_volume_10d": 10_000_000,
    }
    rows = pd.DataFrame(
        [
            {**base, "symbol": "PASS.NS"},
            {**base, "symbol": "STALE.NS", "data_quality_flags": "stale_data"},
            {**base, "symbol": "ILLIQ.NS", "avg_volume_10d": 1_000},
        ]
    )

    with patch("app_routes.stocks._duck_query", return_value=rows):
        response = client.get("/api/multibagger-hunt")

    assert response.status_code == 200
    payload = response.json()
    assert [row["symbol"] for row in payload] == ["PASS.NS"]
    assert payload[0]["trust_gate_pass"] is True
    assert payload[0]["trust_gate_reasons"] == ["PASS"]
    assert payload[0]["liquidity_score"] == 100.0
