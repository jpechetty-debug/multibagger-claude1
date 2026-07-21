import pytest
import yfinance as yf
from unittest.mock import patch

def test_yf_is_patched():
    # Make sure yf_patch is loaded
    import modules.adapters.yf_patch 
    
    assert getattr(yf, "_is_patched", False)

@patch("modules.adapters.yf_patch.get_yf_session")
def test_patched_ticker_uses_session(mock_get_session):
    import modules.adapters.yf_patch
    
    # Passing no session should trigger injection
    t = yf.Ticker("RELIANCE.NS")
    mock_get_session.assert_called()

@patch("modules.adapters.yf_patch.get_yf_session")
def test_patched_download_uses_session(mock_get_session):
    import modules.adapters.yf_patch
    
    # We mock the _original_download so we don't actually hit the network
    with patch("modules.adapters.yf_patch._original_download") as mock_orig:
        yf.download("RELIANCE.NS", period="1d")
        
        mock_get_session.assert_called()
        
        # Verify the session was passed down to the original function
        mock_orig.assert_called_once()
        assert "session" in mock_orig.call_args[1]
