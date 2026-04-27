# modules/auth.py
import os
from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from modules.structured_logger import SovereignLogger

api_logger = SovereignLogger("sovereign.api")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def get_api_key(api_key: str = Depends(api_key_header)):
    """Dependency to validate the X-API-Key header. Hard-fails if not configured."""
    expected_key = os.getenv("SOVEREIGN_API_KEY")
    
    if not expected_key:
        api_logger.error("SOVEREIGN_API_KEY not set in environment. Access denied for security.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not configured — API key missing. Check SOVEREIGN_API_KEY.",
        )
    
    if api_key != expected_key:
        api_logger.warning("Invalid API key attempt detected.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Sovereign API Key",
        )
    return api_key
