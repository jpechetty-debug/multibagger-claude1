"""
ops/ablation_score_feature.py

Ablation study: does including the rule-based `score` in EXTENDED_FEATURES
(alongside its own raw constituents like cfo_pat_ratio, fii_change_3m,
dii_change_3m, pe_ratio, roce, etc.) materially change model behavior
versus training on raw primitives only?

This does NOT modify modules/hybrid_scoring.py or feature_factory.py.
It monkeypatches modules.hybrid_scoring.FEATURES for the duration of each
variant's run (walk_forward_validate and check_shap_dominance both read
that module-level global directly), then restores it. Nothing here
retrains or overwrites the production model artifact.

Usage:
    python ops/ablation_score_feature.py
    python ops/ablation_score_feature.py --top-n 20 50 --out ablation_report.json

Reuses (does not reimplement):
    - modules.hybrid_scoring._build_training_frame   (PIT -> forward-return labels)
    - modules.hybrid_scoring.walk_forward_validate    (expanding quarterly windows,
      same HOLDOUT_START/HOLDOUT_END exclusion as production training)
    - modules.hybrid_scoring._make_xgb_regressor      (same _XGB_PARAMS)
    - modules.hybrid_scoring._sanitize_features
    - modules.hybrid_scoring.check_shap_dominance
    - modules.holdout.split_holdout
    - modules.pit_auditor.sanitize
"""

from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import shap

import modules.hybrid_scoring as hs
from modules.data_layer.db_utils import get_db_connection
from modules.pit_auditor import sanitize
from core.observability.logger import get_logger

logger = get_logger("ops.ablation_score_feature")

VARIANT_NAME_BASELINE = "baseline_with_score"
VARIANT_NAME_ABLATED = "ablated_without_score"


# ---------------------------------------------------------------------------
# Feature-set monkeypatch (scoped, always restored)
# ---------------------------------------------------------------------------

@contextmanager
def _feature_set(features: list[str]):
    """Temporarily point modules.hybrid_scoring.FEATURES at `features`.

    walk_forward_validate() and check_shap_dominance() both read the
    module-level FEATURES global directly rather than accepting a
    parameter, so this is the least invasive way to run both variants
    through the project's real validation path without editing
    hybrid_scoring.py.
    """
    original = hs.FEATURES
    hs.FEATURES = list(features)
    try:
        yield
    finally:
        hs.FEATURES = original


# ---------------------------------------------------------------------------
# Data loading — mirrors train_hybrid_model() steps 1-4
# ---------------------------------------------------------------------------

def load_training_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (train_only, holdout_only), identical to the production
    training pipeline's data prep (PIT extraction -> sanitize -> forward
    returns -> holdout split)."""
    with get_db_connection("stocks.db") as conn:
        raw_df = pd.read_sql(
            """
            SELECT symbol, as_of_date,
                   source_updated_at AS report_date,
                   price             AS pit_price,
                   score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                   debt_equity, cfo_pat_ratio, market_cap_cr,
                   ret_1m, ret_3m, ret_6m,
                   vol_breakout, dist_from_52w_high, roce
            FROM fundamentals_pit
            """,
            conn,
        )
    df = sanitize(raw_df)
    if df.empty and not raw_df.empty:
        logger.warning("PIT Auditor quarantined all rows — using raw fallback")
        df = raw_df

    if len(df) < 20:
        raise SystemExit(
            f"Only {len(df)} PIT rows available (need >= 20) — can't run a "
            "meaningful ablation. Run a few more full scans first."
        )

    train_df = hs._build_training_frame(df)
    if train_df.empty or len(train_df) < 10:
        raise SystemExit(
            f"Only {len(train_df)} rows with valid forward-return targets (need >= 10). "
            "Ablation requires real historical data, not synthetic labels."
        )

    try:
        from modules.holdout import split_holdout
        train_only, holdout_only = split_holdout(train_df)
    except Exception as exc:
        logger.warning("Holdout split failed — using all data", error=str(exc))
        train_only, holdout_only = train_df, pd.DataFrame()

    return train_only, holdout_only


def load_current_snapshot() -> pd.DataFrame:
    """Latest per-symbol row from fundamentals_pit — the 'live universe'
    used to compare how today's rankings would differ between variants."""
    with get_db_connection("stocks.db") as conn:
        raw_df = pd.read_sql(
            """
            SELECT symbol, as_of_date,
                   score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                   debt_equity, cfo_pat_ratio, market_cap_cr,
                   ret_1m, ret_3m, ret_6m,
                   vol_breakout, dist_from_52w_high, roce
            FROM fundamentals_pit
            """,
            conn,
        )
    if raw_df.empty:
        return raw_df
    raw_df["as_of_date"] = pd.to_datetime(raw_df["as_of_date"], errors="coerce")
    raw_df = raw_df.sort_values("as_of_date")
    latest = raw_df.groupby("symbol", as_index=False).tail(1).reset_index(drop=True)
    return latest


# ---------------------------------------------------------------------------
# Per-variant run
# ---------------------------------------------------------------------------

@dataclass
class VariantResult:
    name: str
    features: list[str]
    walk_forward: dict = field(default_factory=dict)
    shap_dominance_passes: bool | None = None
    shap_dominance_reason: str = ""
    shap_importance: dict[str, float] = field(default_factory=dict)
    snapshot_predictions: pd.Series | None = None  # symbol-indexed


def run_variant(
    name: str,
    features: list[str],
    train_only: pd.DataFrame,
    snapshot: pd.DataFrame,
) -> VariantResult:
    logger.info(f"--- Running variant: {name} ---", n_features=len(features))
    result = VariantResult(name=name, features=features)

    with _feature_set(features):
        # 1. Walk-forward validation (expanding quarterly windows, same
        #    HOLDOUT_START/END exclusion as production).
        result.walk_forward = hs.walk_forward_validate(train_only)

        # 2. Production-style fit on train_only for SHAP + snapshot ranking.
        X = hs._sanitize_features(train_only[features])
        y = train_only["forward_return"]
        model = hs._make_xgb_regressor()
        model.fit(X, y)

        passes, reason, importance = hs.check_shap_dominance(model, X)
        result.shap_dominance_passes = passes
        result.shap_dominance_reason = reason
        result.shap_importance = importance

        # 3. Predict on the current live snapshot for ranking comparison.
        if not snapshot.empty:
            X_snap = hs._sanitize_features(
                pd.DataFrame({f: snapshot.get(f, np.nan) for f in features})
            )
            preds = model.predict(X_snap)
            result.snapshot_predictions = pd.Series(
                preds, index=snapshot["symbol"].values, name=name
            )

    return result


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _spearman(a: pd.Series, b: pd.Series) -> float | None:
    aligned = pd.concat([a, b], axis=1).dropna()
    if len(aligned) < 3:
        return None
    r = aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method="spearman")
    return float(r) if np.isfinite(r) else None


def _top_n_overlap(a: pd.Series, b: pd.Series, n: int) -> dict:
    top_a = set(a.sort_values(ascending=False).head(n).index)
    top_b = set(b.sort_values(ascending=False).head(n).index)
    inter = top_a & top_b
    union = top_a | top_b
    return {
        "n": n,
        "overlap_count": len(inter),
        "overlap_pct_of_n": round(100 * len(inter) / n, 1) if n else None,
        "jaccard": round(len(inter) / len(union), 4) if union else None,
        "entered": sorted(top_b - top_a),   # in ablated top-N, not in baseline
        "dropped": sorted(top_a - top_b),   # in baseline top-N, not in ablated
    }


def compare(baseline: VariantResult, ablated: VariantResult, top_ns: list[int]) -> dict:
    report: dict = {
        "baseline": {
            "n_features": len(baseline.features),
            "walk_forward": baseline.walk_forward,
            "shap_dominance_passes": baseline.shap_dominance_passes,
            "shap_dominance_reason": baseline.shap_dominance_reason,
            "shap_importance_top10": dict(
                sorted(baseline.shap_importance.items(), key=lambda kv: -kv[1])[:10]
            ),
        },
        "ablated": {
            "n_features": len(ablated.features),
            "walk_forward": ablated.walk_forward,
            "shap_dominance_passes": ablated.shap_dominance_passes,
            "shap_dominance_reason": ablated.shap_dominance_reason,
            "shap_importance_top10": dict(
                sorted(ablated.shap_importance.items(), key=lambda kv: -kv[1])[:10]
            ),
        },
    }

    wf_b, wf_a = baseline.walk_forward, ablated.walk_forward
    if wf_b.get("status") == "OK" and wf_a.get("status") == "OK":
        report["walk_forward_delta"] = {
            "spearman_ic":         _delta(wf_b.get("spearman_ic"), wf_a.get("spearman_ic")),
            "hit_rate":            _delta(wf_b.get("hit_rate"), wf_a.get("hit_rate")),
            "top_quantile_sharpe": _delta(wf_b.get("top_quantile_sharpe"), wf_a.get("top_quantile_sharpe")),
            "oos_r2":              _delta(wf_b.get("oos_r2"), wf_a.get("oos_r2")),
        }
    else:
        report["walk_forward_delta"] = {
            "note": "one or both variants skipped walk-forward — see status/reason above"
        }

    if baseline.snapshot_predictions is not None and ablated.snapshot_predictions is not None:
        report["ranking_comparison"] = {
            "spearman_rank_correlation": _spearman(
                baseline.snapshot_predictions, ablated.snapshot_predictions
            ),
            "top_n_overlap": {
                n: _top_n_overlap(baseline.snapshot_predictions, ablated.snapshot_predictions, n)
                for n in top_ns
            },
        }
    else:
        report["ranking_comparison"] = {"note": "no current snapshot available"}

    return report


def _delta(b, a):
    if b is None or a is None:
        return None
    return {"baseline": round(b, 4), "ablated": round(a, 4), "diff": round(a - b, 4)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-n", type=int, nargs="+", default=[20, 50])
    parser.add_argument("--out", type=str, default=None, help="Optional path to write JSON report")
    args = parser.parse_args()

    train_only, _holdout_only = load_training_frame()
    snapshot = load_current_snapshot()

    baseline_features = list(hs.FEATURES)  # exactly what's shipped today
    if "score" not in baseline_features:
        raise SystemExit(
            "'score' is not currently in hybrid_scoring.FEATURES — nothing to ablate."
        )
    ablated_features = [f for f in baseline_features if f != "score"]

    baseline = run_variant(VARIANT_NAME_BASELINE, baseline_features, train_only, snapshot)
    ablated = run_variant(VARIANT_NAME_ABLATED, ablated_features, train_only, snapshot)

    report = compare(baseline, ablated, args.top_n)

    print(json.dumps(report, indent=2, default=str))

    if args.out:
        with open(args.out, "w") as fh:
            json.dump(report, fh, indent=2, default=str)
        logger.info(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
