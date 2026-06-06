import pytest
from unittest.mock import patch
import pandas as pd
from fastapi.testclient import TestClient
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from main import app
from modules.scoring.engine import calculate_institutional_score
from modules.scoring.factors import _resolve_mode_and_weights

def test_pledge_penalty():
    """Verify that pledge > 0 correctly penalises the conviction score."""
    base_data = {
        "symbol": "TEST.NS",
        "market_cap_cr": 1000,
        "sales_cagr_5y": 20,
        "avg_roe_5y": 20,
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
    
    with patch("db.db_core.duck_conn.execute") as mock_execute:
        # Mock the dataframe return
        mock_execute.return_value.df.return_value = pd.DataFrame()
        
        response = client.get("/api/multibagger-hunt")
        assert response.status_code == 200
        
        mock_execute.assert_called_once()
        query = mock_execute.call_args[0][0]
        
        assert "CAST(sales_cagr_5y AS DOUBLE) >= 15" in query, "sales_cagr_5y threshold should be >= 15"
        assert "CAST(avg_roe_5y AS DOUBLE) >= 15" in query, "avg_roe_5y threshold should be >= 15"
