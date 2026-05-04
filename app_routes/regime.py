from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

import config
import modules.data_service as market_data_module
import modules.dependencies as deps
from app_routes.contracts import RegimeStatusResponse

router = APIRouter()
_REGIME_IO_TIMEOUT_SECONDS = 5.0

_FORCE_REGIME_MAP = {
    "0": "BEAR",
    "1": "BULL",
    "2": "SIDEWAYS",
    "AUTO": None,
    "NONE": None,
    "BEAR": "BEAR",
    "BEARISH": "BEAR",
    "BULL": "BULL",
    "BULLISH": "BULL",
    "VOLATILE": "SIDEWAYS",
    "SIDEWAYS": "SIDEWAYS",
    "VOL": "SIDEWAYS",
}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return float(default)
    return parsed if parsed == parsed else float(default)


def _normalize_regime(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"BULL", "BULLISH", "MOMENTUM"}:
        return "BULL"
    if text in {"BEAR", "BEARISH", "QUALITY"}:
        return "BEAR"
    if text in {"VOLATILE", "SIDEWAYS", "BALANCED", "VALUE", "UNKNOWN"}:
        return "SIDEWAYS"
    if text == "BLACK":
        return "BLACK"
    return "SIDEWAYS"


def _parse_forced_regime(raw_regime: str | None) -> str | None:
    if raw_regime is None:
        return None
    normalized = str(raw_regime).strip().upper()
    if normalized not in _FORCE_REGIME_MAP:
        raise HTTPException(
            status_code=400,
            detail="Invalid regime override. Use BULL, BEAR, SIDEWAYS, AUTO, or 0/1/2.",
        )
    return _FORCE_REGIME_MAP[normalized]


def _build_payload(
    regime_data: dict[str, Any] | None,
    *,
    forced_regime: str | None,
    stale: bool,
    error: str | None = None,
) -> RegimeStatusResponse:
    regime_data = regime_data or {}
    details = dict(regime_data.get("details") or {})
    detected_regime = _normalize_regime(regime_data.get("regime"))
    regime = forced_regime or detected_regime

    votes = regime_data.get("votes")
    if not isinstance(votes, dict):
        votes = {}

    if "vix" not in details:
        details["vix"] = _as_float(regime_data.get("vix"))
    if "vix_threshold" not in details:
        details["vix_threshold"] = _as_float(regime_data.get("vix_threshold"))
    if "momentum_accel" not in details:
        details["momentum_accel"] = _as_float(regime_data.get("momentum_accel"))
    details["detected_regime"] = detected_regime
    if forced_regime:
        details["forced_regime"] = forced_regime

    return RegimeStatusResponse(
        regime=regime,
        vix=_as_float(details.get("vix")),
        vix_threshold=_as_float(details.get("vix_threshold")),
        momentum_accel=_as_float(details.get("momentum_accel")),
        votes=votes,
        is_forced=forced_regime is not None,
        details=details,
        timestamp=datetime.now().isoformat(),
        stale=stale,
        error=error,
    )


@router.get("/api/regime_status", response_model=RegimeStatusResponse)
async def get_regime_status():
    """Return the current regime using the active MarketDataProvider contract."""
    if deps._cache_is_fresh(deps.regime_cache, deps.REGIME_CACHE_TTL_SECONDS):
        return deps.regime_cache["payload"]

    async with deps.regime_cache_lock:
        if deps._cache_is_fresh(deps.regime_cache, deps.REGIME_CACHE_TTL_SECONDS):
            return deps.regime_cache["payload"]

        forced_regime = _parse_forced_regime(config.FORCED_REGIME)
        try:
            provider = market_data_module.MarketDataProvider()
            regime_data = await asyncio.wait_for(
                deps._run_blocking(provider.get_market_regime),
                timeout=_REGIME_IO_TIMEOUT_SECONDS,
            )
            payload = _build_payload(
                regime_data,
                forced_regime=forced_regime,
                stale=False,
            )
            deps._cache_set(deps.regime_cache, payload.model_dump())
            return payload
        except Exception as exc:
            deps.runtime_logger.warning("Regime status fallback engaged", error=str(exc))

            cached_payload = deps.regime_cache.get("payload")
            if isinstance(cached_payload, dict):
                return _build_payload(
                    dict(cached_payload),
                    forced_regime=forced_regime,
                    stale=True,
                    error=str(exc),
                )

            return _build_payload(
                {},
                forced_regime=forced_regime,
                stale=True,
                error=str(exc),
            )


@router.post("/api/admin/force_regime")
async def force_regime(regime: str | None = None):
    """Admin override for market regime using labels or AUTO reset."""
    normalized = _parse_forced_regime(regime)

    if normalized is None:
        config.FORCED_REGIME = None
        deps.runtime_logger.info("Regime override cleared; resuming auto mode")
        reported_regime = "AUTO"
    else:
        config.FORCED_REGIME = normalized
        deps.runtime_logger.info("Regime forced by administrator", regime=normalized)
        reported_regime = normalized

    deps._cache_invalidate(deps.regime_cache)
    return {"status": "success", "regime": reported_regime}
