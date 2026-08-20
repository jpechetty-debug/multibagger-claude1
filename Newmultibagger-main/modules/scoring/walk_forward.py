"""
Walk-forward validation framework for XGBoost scoring models.

Extracted from modules/hybrid_scoring.py.
Implements expanding-window walk-forward with holdout exclusion.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from modules.scoring.utils import _finite_or_none, _spearman_ic, _top_quantile_sharpe

try:
    from core.observability.logger import get_logger
    _log = get_logger("modules.scoring.walk_forward")
except Exception:
    import logging
    _log = logging.getLogger("modules.scoring.walk_forward")


WALK_FORWARD_REPORT_PATH = os.path.join("runtime", "models", "xgboost_walk_forward.json")

# Holdout: 2018-2020 is locked off — never used in training or WF folds.
HOLDOUT_START = "2018-01-01"
HOLDOUT_END = "2020-12-31"


@dataclass
class WalkForwardWindow:
    test_period: str
    train_rows: int
    test_rows: int
    fold_ic: float | None = None
    fold_hit_rate: float | None = None
    fold_top_sharpe: float | None = None


@dataclass
class WalkForwardResult:
    status: str  # "OK" | "SKIPPED"
    reason: str = ""
    folds: int = 0
    rows: int = 0
    oos_r2: float | None = None
    mae: float | None = None
    rmse: float | None = None
    spearman_ic: float | None = None
    hit_rate: float | None = None
    top_quantile_sharpe: float | None = None
    holdout_rows_excluded: int = 0
    windows: list[WalkForwardWindow] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "folds": self.folds,
            "rows": self.rows,
            "oos_r2": self.oos_r2,
            "mae": self.mae,
            "rmse": self.rmse,
            "spearman_ic": self.spearman_ic,
            "hit_rate": self.hit_rate,
            "top_quantile_sharpe": self.top_quantile_sharpe,
            "holdout_rows_excluded": self.holdout_rows_excluded,
            "windows": [
                {
                    "test_period": w.test_period,
                    "train_rows": w.train_rows,
                    "test_rows": w.test_rows,
                    "fold_ic": w.fold_ic,
                    "fold_hit_rate": w.fold_hit_rate,
                    "fold_top_sharpe": w.fold_top_sharpe,
                }
                for w in self.windows
            ],
        }


def _save_walk_forward_report(metrics: dict) -> None:
    os.makedirs(os.path.dirname(WALK_FORWARD_REPORT_PATH), exist_ok=True)
    with open(WALK_FORWARD_REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    _log.info("Walk-forward report saved", path=WALK_FORWARD_REPORT_PATH)


def load_walk_forward_report() -> dict | None:
    """Load last persisted walk-forward report, or None if not yet trained."""
    if not os.path.exists(WALK_FORWARD_REPORT_PATH):
        return None
    with open(WALK_FORWARD_REPORT_PATH, encoding="utf-8") as fh:
        return json.load(fh)
