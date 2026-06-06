# modules/auth.py
import os
import time
import hashlib

from fastapi import Depends, HTTPException, status, Request, BackgroundTasks
from fastapi.security import APIKeyHeader
from cachetools import TTLCache

from core.observability.logger import get_logger
from db.db_core import execute_sql

api_logger = get_logger("sovereign.api")

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Track requests per minute for rate limiting (sliding window up to 60s)
_RATE_LIMIT_CACHE = TTLCache(maxsize=1000, ttl=60)

def _increment_usage_in_bg(key_hash: str):
    """Background task to increment the usage counter."""
    try:
        execute_sql("UPDATE api_keys SET total_usage = total_usage + 1, updated_at = CURRENT_TIMESTAMP WHERE key_hash = :key_hash", {"key_hash": key_hash})
    except Exception as e:
        api_logger.error("Failed to increment usage for key", error=str(e))

def get_api_key(request: Request, background_tasks: BackgroundTasks, api_key: str | None = Depends(api_key_header)):
    """Dependency to validate the X-API-Key header or query parameter for WebSockets."""
    expected_key = os.getenv("SOVEREIGN_API_KEY")

    # For WebSockets, allow verification via query params 'token' or 'api_key'
    if request.scope.get("type") == "websocket":
        api_key = request.query_params.get("token") or request.query_params.get("api_key") or api_key

    if not api_key:
        api_logger.error("API key missing in request.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Server not configured — API key missing.",
        )

    # Allow fallback master key if defined
    if expected_key and api_key == expected_key:
        return api_key

    # Check against database
    key_hash = hashlib.sha256(api_key.encode(), usedforsecurity=False).hexdigest()
    query = "SELECT is_active, rate_limit_rpm FROM api_keys WHERE key_hash = :key_hash"
    results = execute_sql(query, {"key_hash": key_hash}, fetch_all=True)
    
    if not results:
        api_logger.warning("Invalid API key attempt detected.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Sovereign API Key")
        
    record = results[0]
    if not record["is_active"]:
        api_logger.warning("Revoked API key attempt detected.")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key has been revoked")
        
    # Rate limiting
    rate_limit = record["rate_limit_rpm"]
    now = time.time()
    
    if key_hash not in _RATE_LIMIT_CACHE:
        _RATE_LIMIT_CACHE[key_hash] = []
        
    # Clean up old timestamps (sliding window)
    timestamps = _RATE_LIMIT_CACHE[key_hash]
    timestamps = [ts for ts in timestamps if now - ts < 60]
    
    if len(timestamps) >= rate_limit:
        api_logger.warning("Rate limit exceeded for API key.")
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Rate limit exceeded")
        
    timestamps.append(now)
    _RATE_LIMIT_CACHE[key_hash] = timestamps
    
    # Increment usage counter asynchronously
    background_tasks.add_task(_increment_usage_in_bg, key_hash)
    
    return api_key
