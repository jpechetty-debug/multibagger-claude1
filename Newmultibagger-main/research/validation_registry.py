"""
research/validation_registry.py

Tracks metadata for every validation run (holdout, regime, ablation, etc.)
This prevents losing context on which model or feature set produced a given result.
"""
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from core.observability.logger import get_logger

logger = get_logger("research.validation_registry")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_FILE = PROJECT_ROOT / "runtime" / "validation_registry.json"
VALIDATION_DIR = PROJECT_ROOT / "validation"

class ValidationRegistry:
    def __init__(self):
        self.file_path = REGISTRY_FILE
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        VALIDATION_DIR.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text(json.dumps({"runs": []}, indent=4))
            
    def _load(self) -> dict:
        try:
            return json.loads(self.file_path.read_text())
        except Exception:
            return {"runs": []}
            
    def _save(self, data: dict):
        self.file_path.write_text(json.dumps(data, indent=4))
        
    def register_run(self, 
                     model_version: str, 
                     training_window: str, 
                     holdout_window: str, 
                     feature_set: str, 
                     hyperparameters: dict) -> str:
        """
        Register a new validation run and return its unique run_id.
        """
        run_id = str(uuid.uuid4())
        run_data = {
            "run_id": run_id,
            "run_timestamp": datetime.utcnow().isoformat() + "Z",
            "model_version": model_version,
            "training_window": training_window,
            "holdout_window": holdout_window,
            "feature_set": feature_set,
            "hyperparameters": hyperparameters
        }
        
        data = self._load()
        data["runs"].append(run_data)
        self._save(data)
        logger.info(f"Registered new validation run: {run_id}")
        return run_id
        
    def get_run(self, run_id: str) -> Optional[dict]:
        data = self._load()
        for r in data["runs"]:
            if r["run_id"] == run_id:
                return r
        return None
