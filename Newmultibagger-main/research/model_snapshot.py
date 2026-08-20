"""
research/model_snapshot.py

Handles freezing the model state during a validation run.
Saves the actual model artifact, feature list, hyperparams, and git hash.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List

from core.observability.logger import get_logger

logger = get_logger("research.model_snapshot")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = PROJECT_ROOT / "validation" / "snapshots"

class ModelSnapshotManager:
    def __init__(self):
        self.snapshot_dir = SNAPSHOT_DIR
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_git_hash(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except Exception as e:
            logger.warning(f"Failed to get git hash: {e}")
            return "unknown_hash"

    def create_snapshot(self, 
                        run_id: str, 
                        model_path: str, 
                        features: List[str], 
                        hyperparameters: Dict[str, Any],
                        training_window: str,
                        holdout_window: str) -> str:
        """
        Creates an immutable snapshot of the model and its metadata for a given run.
        """
        run_snapshot_dir = self.snapshot_dir / run_id
        run_snapshot_dir.mkdir(exist_ok=True)
        
        # 1. Copy model file
        model_src = Path(model_path)
        if model_src.exists():
            model_dest = run_snapshot_dir / f"model_{run_id}.json"
            shutil.copy2(model_src, model_dest)
        else:
            logger.error(f"Model file not found to snapshot: {model_path}")
            model_dest = None

        # 2. Save snapshot metadata
        snapshot_meta = {
            "run_id": run_id,
            "git_hash": self._get_git_hash(),
            "training_window": training_window,
            "holdout_window": holdout_window,
            "hyperparameters": hyperparameters,
            "features": features,
            "model_file": str(model_dest.name) if model_dest else None
        }
        
        meta_path = run_snapshot_dir / "snapshot_meta.json"
        meta_path.write_text(json.dumps(snapshot_meta, indent=4))
        
        logger.info(f"Created model snapshot for run {run_id}")
        return str(run_snapshot_dir)
