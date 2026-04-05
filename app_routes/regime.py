from fastapi import APIRouter
import modules.dependencies as deps
import config

router = APIRouter()

@router.get("/api/regime_status")
async def get_regime_status():
    """Fetch current Market Regime (Bullish/Bearish/Volatile) from HMM."""
    try:
        from modules.regime_hmm import RegimeHMM
        if deps._cache_is_fresh(deps.regime_cache, 3600):
            return deps.regime_cache["payload"]

        async with deps.regime_cache_lock:
            if deps._cache_is_fresh(deps.regime_cache, 3600):
                return deps.regime_cache["payload"]

            hmm = RegimeHMM()
            regime = await hmm.get_current_regime()
            
            # Forced override?
            if config.FORCED_REGIME:
                original = regime
                regime = config.FORCED_REGIME
                deps.runtime_logger.info("Regime override active", original=original, forced=regime)

            # Map index to state
            state_map = {0: "BEARISH", 1: "BULLISH", 2: "VOLATILE"}
            label = state_map.get(regime, "UNKNOWN")
            
            payload = {
                "regime": regime,
                "label": label,
                "confidence": 0.85, # HMM posterior probability placeholder
                "recommendation": "Risk-On" if label=="BULLISH" else "De-risk/Hedge",
                "forced": config.FORCED_REGIME is not None
            }
            deps._cache_set(deps.regime_cache, payload)
            return payload
    except Exception as e:
        return {"error": str(e)}

@router.post("/api/admin/force_regime")
async def force_regime(regime: int | None = None):
    """Admin override for market regime (0=Bear, 1=Bull, 2=Vol, None=Auto)."""
    try:
        if regime is None:
            config.FORCED_REGIME = None
            deps.runtime_logger.info("Regime override cleared; resuming auto mode")
        else:
            config.FORCED_REGIME = regime
            deps.runtime_logger.info("Regime forced by administrator", regime=regime)

        deps._cache_invalidate(deps.regime_cache)
        return {"status": "success", "regime": regime}
    except Exception as e:
        return {"error": str(e)}
