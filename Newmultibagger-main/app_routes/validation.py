"""
app_routes/validation.py

Exposes Sovereign AI Validation outputs (Month 4 deliverables) to the React/Vite dashboard.
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/validation", tags=["validation"])
VALIDATION_DIR = Path(__file__).resolve().parents[1] / "validation"

def _load_json(filename: str) -> dict:
    filepath = VALIDATION_DIR / filename
    if not filepath.exists():
        return {}
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read {filename}: {str(e)}")

@router.get("/trust")
async def get_trust_score():
    return _load_json("trust.json")

@router.get("/holdout")
async def get_holdout_validation():
    return _load_json("holdout.json")

@router.get("/regime")
async def get_regime_validation():
    return _load_json("regime.json")

@router.get("/shap")
async def get_explainability_audit():
    return _load_json("shap.json")

@router.get("/feature-stability")
async def get_feature_stability():
    return _load_json("feature_stability.json")

@router.get("/ablation")
async def get_ablation_impact():
    return _load_json("ablation.json")

@router.get("/compounder")
async def get_compounder_capture():
    return _load_json("compounder.json")

@router.get("/dashboard")
async def get_full_dashboard_state():
    """Aggregates all validation modules into a single payload for the UI."""
    return {
        "trust": _load_json("trust.json"),
        "holdout": _load_json("holdout.json"),
        "regime": _load_json("regime.json"),
        "shap": _load_json("shap.json"),
        "stability": _load_json("feature_stability.json"),
        "ablation": _load_json("ablation.json"),
        "compounder": _load_json("compounder.json")
    }
