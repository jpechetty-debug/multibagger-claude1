"""
research/trust_score.py

Aggregates outputs from all validation modules to compute the Sovereign Trust Score.
Outputs to validation/trust.json.
"""

import json
from pathlib import Path

from core.observability.logger import get_logger
from research.validation_registry import ValidationRegistry

logger = get_logger("research.trust_score")
VALIDATION_DIR = Path(__file__).resolve().parents[1] / "validation"

def load_validation_file(filename: str) -> dict:
    file_path = VALIDATION_DIR / filename
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def compute_trust_score() -> dict:
    logger.info("Computing Composite Trust Score")
    
    holdout = load_validation_file("holdout.json")
    regime = load_validation_file("regime.json")
    ablation = load_validation_file("ablation.json")
    stability = load_validation_file("feature_stability.json")
    compounder = load_validation_file("compounder.json")
    shap_data = load_validation_file("shap.json")
    
    score_components = {
        "holdout": 0.0,
        "stability": 0.0,
        "ablation": 0.0,
        "compounder": 0.0,
        "shap": 0.0
    }
    
    # 1. Holdout (Max 40) - Based on Info Ratio & Sortino & Base Passed Flag
    if holdout:
        if holdout.get("passed", False):
            score_components["holdout"] += 20.0
            
        metrics = holdout.get("metrics", {})
        info_ratio = metrics.get("Top20 Information Ratio", 0.0)
        sortino = metrics.get("Top20 Sortino", 0.0)
        
        # Add up to 10 points for info ratio > 1.0
        if info_ratio > 0:
            score_components["holdout"] += min(10.0, info_ratio * 5)
            
        # Add up to 10 points for sortino > 1.5
        if sortino > 0:
            score_components["holdout"] += min(10.0, sortino * 3)
            
    # 2. Stability (Max 20)
    if stability:
        metrics = stability.get("metrics", {})
        alerts = metrics.get("drifted_features", [])
        if stability.get("passed", False):
            score_components["stability"] = 20.0
        else:
            # Deduct 5 points per drifted feature
            score_components["stability"] = max(0.0, 20.0 - (len(alerts) * 5))
            
    # 3. Ablation (Max 20)
    if ablation:
        metrics = ablation.get("metrics", {})
        impact = metrics.get("ablation_impact", {})
        # If removing Rule_Score or other features drops Sharpe heavily, we gain points (shows model uses them)
        total_impact = 0.0
        for group, res in impact.items():
            total_impact += res.get("sharpe_impact", 0.0)
        
        if total_impact > 0:
            score_components["ablation"] = min(20.0, 10 + (total_impact * 10))
        else:
            score_components["ablation"] = 10.0 # Base points just for running it
            
    # 4. Compounder Capture (Max 15)
    if compounder:
        metrics = compounder.get("metrics", {})
        capture_rate = metrics.get("overall_weighted_capture_rate", 0.0)
        score_components["compounder"] = min(15.0, capture_rate * 15.0)
        
    # 5. Explainability / SHAP (Max 5)
    if shap_data:
        if shap_data.get("passed", False):
            score_components["shap"] = 5.0
            
    total_score = sum(score_components.values())
    
    trust_report = {
        "trust_score": float(total_score),
        "passed": bool(total_score > 80.0),
        "components": score_components,
        "run_status": {
            "holdout": bool(holdout),
            "regime": bool(regime),
            "ablation": bool(ablation),
            "stability": bool(stability),
            "compounder": bool(compounder),
            "shap": bool(shap_data)
        }
    }
    
    out_file = VALIDATION_DIR / "trust.json"
    out_file.parent.mkdir(exist_ok=True)
    out_file.write_text(json.dumps(trust_report, indent=4))
    
    logger.info(f"Trust Score calculated: {total_score:.2f}/100. Saved to validation/trust.json")
    return trust_report

if __name__ == "__main__":
    result = compute_trust_score()
    print(json.dumps(result, indent=2))
