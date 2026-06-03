# modules/auth.py
import os

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import APIKeyHeader

from modules.structured_logger import SovereignLogger

api_logger = SovereignLogger("sovereign.api")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


def get_api_key(request: Request, api_key: str | None = Depends(api_key_header)):
    """Dependency to validate the X-API-Key header or query parameter for WebSockets."""
    expected_key = os.getenv("SOVEREIGN_API_KEY")

    if not expected_key:
        api_logger.error("SOVEREIGN_API_KEY not set in environment. Access denied for security.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Server not configured — API key missing. Check SOVEREIGN_API_KEY.",
        )

    # For WebSockets, allow verification via query params 'token' or 'api_key'
    if request.scope.get("type") == "websocket":
        query_token = request.query_params.get("token") or request.query_params.get("api_key")
        if query_token == expected_key:
            return query_token

    if api_key != expected_key:
        api_logger.warning("Invalid API key attempt detected.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Sovereign API Key",
        )
    return api_key
