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

def walk_forward_validate(
    train_df: pd.DataFrame,
    min_train_rows: int = 10,
    min_train_periods: int = 4,
) -> dict:
    """Expanding-window walk-forward validation for the hybrid XGBoost scorer."""
    required = {"symbol", "as_of_date", "forward_return", *FEATURES}
    missing = required - set(train_df.columns)
    if missing:
        return WalkForwardResult(
            status="SKIPPED",
            reason=f"missing columns: {sorted(missing)}",
        ).to_dict()

    df = train_df.copy()
    df["as_of_date"]    = pd.to_datetime(df["as_of_date"], errors="coerce")
    df["forward_return"]= pd.to_numeric(df["forward_return"], errors="coerce")
    df = df.dropna(subset=["as_of_date", "forward_return"]).sort_values("as_of_date")

    holdout_mask         = df["as_of_date"].between(HOLDOUT_START, HOLDOUT_END)
    holdout_rows_excluded= int(holdout_mask.sum())
    df = df[~holdout_mask]

    if len(df) < min_train_rows:
        return WalkForwardResult(
            status="SKIPPED",
            reason="not enough valid rows",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    df["test_period"] = df["as_of_date"].dt.to_period("Q")
    periods = sorted(df["test_period"].dropna().unique())
    if len(periods) <= min_train_periods:
        return WalkForwardResult(
            status="SKIPPED",
            reason="not enough quarterly periods",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    all_predictions: list[pd.DataFrame] = []
    windows: list[WalkForwardWindow]    = []

    for test_period in periods[min_train_periods:]:
        test_start = test_period.start_time
        train_fold = df[df["as_of_date"] < test_start]
        test_fold  = df[df["test_period"] == test_period]

        if len(train_fold) < min_train_rows or test_fold.empty:
            continue

        model   = _make_xgb_regressor()
        X_train = _sanitize_features(train_fold[FEATURES])
        y_train = train_fold["forward_return"]
        X_test  = _sanitize_features(test_fold[FEATURES])

        model.fit(X_train, y_train, eval_set=[(X_train, y_train)], verbose=False)

        fold_preds = test_fold[["symbol", "as_of_date", "forward_return"]].copy()
        fold_preds["prediction"] = model.predict(X_test)
        fold_preds["test_period"]= str(test_period)
        all_predictions.append(fold_preds)

        ft = pd.to_numeric(fold_preds["forward_return"], errors="coerce")
        fp = pd.to_numeric(fold_preds["prediction"],     errors="coerce")
        fold_ic       = _spearman_ic(ft, fp)
        fold_hit_rate = _finite_or_none(((ft > 0) == (fp > 0)).mean())
        fold_sharpe   = _top_quantile_sharpe(
            ft[fp.nlargest(max(1, int(len(fp) * 0.2))).index],
        )
        windows.append(WalkForwardWindow(
            test_period=str(test_period),
            train_rows=int(len(train_fold)),
            test_rows=int(len(test_fold)),
            fold_ic=fold_ic,
            fold_hit_rate=fold_hit_rate,
            fold_top_sharpe=fold_sharpe,
        ))

    if not all_predictions:
        return WalkForwardResult(
            status="SKIPPED",
            reason="no valid walk-forward folds",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    pred_df = pd.concat(all_predictions, ignore_index=True)
    y_true  = pd.to_numeric(pred_df["forward_return"], errors="coerce")
    y_pred  = pd.to_numeric(pred_df["prediction"],     errors="coerce")
    valid   = y_true.notna() & y_pred.notna()
    y_true, y_pred = y_true[valid], y_pred[valid]

    if y_true.empty:
        return WalkForwardResult(
            status="SKIPPED",
            reason="all predictions invalid",
            holdout_rows_excluded=holdout_rows_excluded,
        ).to_dict()

    residual = y_true - y_pred
    ss_res = float(np.square(residual).sum())
    ss_tot = float(np.square(y_true - y_true.mean()).sum())

    return WalkForwardResult(
        status="OK",
        folds=len(windows),
        rows=int(len(y_true)),
        oos_r2=_finite_or_none(1 - ss_res / ss_tot if ss_tot > 0 else np.nan),
        mae=_finite_or_none(np.abs(residual).mean()),
        rmse=_finite_or_none(np.sqrt(np.square(residual).mean())),
        spearman_ic=_spearman_ic(y_true, y_pred),
        hit_rate=_finite_or_none(((y_true > 0) == (y_pred > 0)).mean()),
        top_quantile_sharpe=_top_quantile_sharpe(
            y_true[y_pred.nlargest(max(1, int(len(y_pred) * 0.2))).index]
        ),
        holdout_rows_excluded=holdout_rows_excluded,
        windows=windows,
    ).to_dict()


# ---------------------------------------------------------------------------
# Report persistence
# ---------------------------------------------------------------------------

