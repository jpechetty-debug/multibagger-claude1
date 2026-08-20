"""
research/validation_contract.py

Defines the standard data contract for all validation audits in Month 4.
This ensures holdout, regime, ablation, and stability modules all return a unified
JSON-serializable payload structure that the React frontend can consume via FastAPI.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, Any, Optional

@dataclass
class ValidationResult:
    run_id: str
    model_version: str
    validation_type: str
    
    passed: bool
    
    metrics: Dict[str, Any] = field(default_factory=dict)
    charts: Dict[str, Any] = field(default_factory=dict)
    
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def to_dict(self) -> dict:
        return asdict(self)
