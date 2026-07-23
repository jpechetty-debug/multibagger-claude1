# modules/feature_leakage_audit.py
# Sovereign AI — Feature Leakage Audit
# Audits every ML feature for temporal validity and suspicious predictive power.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from modules.hybrid_scoring import FEATURES

# ---------------------------------------------------------------------------
# Feature classification metadata
# ---------------------------------------------------------------------------

# Fundamentals arrive with a known quarterly publication lag (45-90 days),
# so high Spearman-r is expected and does NOT necessarily indicate leakage.
_FUNDAMENTAL_FEATURES: frozenset[str] = frozenset({
    "score", "sales_cagr_5y", "avg_roe_5y", "pe_ratio",
    "debt_equity", "cfo_pat_ratio", "market_cap_cr", "roce",
})

# Momentum features use price history — if prices are calculated with a
# look-ahead date even 1 day in the future, they will leak.
_MOMENTUM_FEATURES: frozenset[str] = frozenset({
    "ret_1m", "ret_3m", "ret_6m", "vol_breakout", "dist_from_52w_high",
})

# Thresholds
SPEARMAN_LEAK_THRESHOLD  = 0.40   # |r| above this → investigate
MOMENTUM_REVIEW_THRESHOLD = 0.15  # momentum features are reviewed at a lower bar


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FeatureVerdict:
    feature: str
    spearman_r: float | None
    classification: str    # "SAFE" | "NEEDS_REVIEW" | "LEAKING"
    reason: str = ""


@dataclass
class LeakageReport:
    verdicts: list[FeatureVerdict] = field(default_factory=list)
    leaking_count: int = 0
    review_count: int = 0

    @property
    def has_leaks(self) -> bool:
        return self.leaking_count > 0

    def to_dict(self) -> dict:
        return {
            "leaking_count": self.leaking_count,
            "review_count": self.review_count,
            "has_leaks": self.has_leaks,
            "verdicts": [
                {
                    "feature": v.feature,
                    "spearman_r": v.spearman_r,
                    "classification": v.classification,
                    "reason": v.reason,
                }
                for v in self.verdicts
            ],
        }


# ---------------------------------------------------------------------------
# Core audit
# ---------------------------------------------------------------------------

def audit_features(
    pit_df: pd.DataFrame,
    forward_return_col: str = "forward_return",
    features: Sequence[str] | None = None,
) -> LeakageReport:
    """Audit each feature for data leakage against forward returns.

    Classification rules:
    - |Spearman r| > SPEARMAN_LEAK_THRESHOLD:
        - Fundamental feature  → NEEDS_REVIEW (known lag may explain it)
        - Momentum feature     → LEAKING (no documented delay justifies this)
    - Momentum feature with |r| > MOMENTUM_REVIEW_THRESHOLD → NEEDS_REVIEW
    - Otherwise → SAFE

    Args:
        pit_df: DataFrame containing feature columns and ``forward_return_col``.
        forward_return_col: Target column name.
        features: Override the feature list (defaults to FEATURES).

    Returns:
        LeakageReport with per-feature verdicts and aggregate counts.
    """
    feature_list = list(features or FEATURES)
    report = LeakageReport()

    if forward_return_col not in pit_df.columns:
        return report

    y = pd.to_numeric(pit_df[forward_return_col], errors="coerce")

    for feat in feature_list:
        if feat not in pit_df.columns:
            report.verdicts.append(
                FeatureVerdict(feat, None, "SAFE", "column missing — zero-filled at inference")
            )
            continue

        x = pd.to_numeric(pit_df[feat], errors="coerce")
        valid = x.notna() & y.notna()

        if valid.sum() < 5:
            report.verdicts.append(
                FeatureVerdict(feat, None, "SAFE", "too few observations for correlation")
            )
            continue

        r = x[valid].corr(y[valid], method="spearman")
        r = float(r) if np.isfinite(r) else 0.0

        abs_r = abs(r)
        if abs_r > SPEARMAN_LEAK_THRESHOLD:
            if feat in _FUNDAMENTAL_FEATURES:
                classification = "NEEDS_REVIEW"
                reason = (
                    f"|r|={abs_r:.3f} > {SPEARMAN_LEAK_THRESHOLD} "
                    f"but fundamental features have a known quarterly publication lag — "
                    f"verify as_of_date ≤ report_release_date"
                )
                report.review_count += 1
            else:
                classification = "LEAKING"
                reason = (
                    f"|r|={abs_r:.3f} > {SPEARMAN_LEAK_THRESHOLD} "
                    f"with no documented publication lag — likely look-ahead bias"
                )
                report.leaking_count += 1
        elif feat in _MOMENTUM_FEATURES and abs_r > MOMENTUM_REVIEW_THRESHOLD:
            classification = "NEEDS_REVIEW"
            reason = (
                f"Momentum feature with |r|={abs_r:.3f} > {MOMENTUM_REVIEW_THRESHOLD} — "
                f"confirm price date ≤ as_of_date"
            )
            report.review_count += 1
        else:
            classification = "SAFE"
            reason = f"|r|={abs_r:.3f}"

        report.verdicts.append(FeatureVerdict(feat, round(r, 4), classification, reason))

    return report


# ---------------------------------------------------------------------------
# Momentum return self-consistency check
# ---------------------------------------------------------------------------

def validate_momentum_returns(
    pit_df: pd.DataFrame,
    tolerance: float = 0.05,
) -> list[dict]:
    """Validate that reported ret_1m matches reconstructed price-based return.

    Any symbol where the reported and computed 1-month returns differ by more
    than ``tolerance × 100 pct-points`` is flagged as a potential look-ahead
    contamination.

    Args:
        pit_df: Must contain 'symbol', 'as_of_date', 'price', and 'ret_1m'.
        tolerance: Fractional mismatch threshold (default 5%).

    Returns:
        List of dicts {'symbol', 'mismatched_rows', 'max_diff_pct'}.
    """
    issues: list[dict] = []
    required = {"symbol", "as_of_date", "price", "ret_1m"}
    if not required.issubset(pit_df.columns):
        return issues

    for sym, group in pit_df.groupby("symbol"):
        group = group.sort_values("as_of_date").copy()
        if len(group) < 2:
            continue

        prices       = pd.to_numeric(group["price"], errors="coerce")
        reported_ret = pd.to_numeric(group["ret_1m"], errors="coerce")
        computed_ret = prices.pct_change() * 100.0          # percentage

        diff = (reported_ret - computed_ret).dropna().abs()
        bad  = diff[diff > tolerance * 100.0]

        if not bad.empty:
            issues.append({
                "symbol":          sym,
                "mismatched_rows": int(len(bad)),
                "max_diff_pct":    float(bad.max()),
            })

    return issues


# ---------------------------------------------------------------------------
# Variance Inflation Factor (multicollinearity check)
# ---------------------------------------------------------------------------

def compute_vif(
    df: pd.DataFrame,
    features: Sequence[str] | None = None,
    threshold: float = 10.0,
) -> list[dict]:
    """Compute VIF for each feature and flag high-multicollinearity features.

    Features with VIF > ``threshold`` (default 10) suggest redundant information
    that may destabilise SHAP attribution without improving predictive accuracy.

    Args:
        df: DataFrame containing feature columns.
        features: Feature list (defaults to FEATURES).
        threshold: VIF above this is flagged as HIGH_COLLINEARITY.

    Returns:
        List of dicts with keys: feature, vif, flag.
    """
    from numpy.linalg import pinv

    feature_list = list(features or FEATURES)
    cols = [f for f in feature_list if f in df.columns]
    if len(cols) < 2:
        return []

    X = df[cols].copy()
    for col in cols:
        X[col] = pd.to_numeric(X[col], errors="coerce").fillna(0.0)

    X_mat = X.values
    if X_mat.shape[0] < 3:
        return []

    # Standardise to avoid scale dominance
    std = X_mat.std(axis=0)
    std[std == 0] = 1.0
    X_std = (X_mat - X_mat.mean(axis=0)) / std

    results = []
    for i, feat in enumerate(cols):
        y_col = X_std[:, i]
        X_rest = np.delete(X_std, i, axis=1)
        try:
            betas     = pinv(X_rest.T @ X_rest) @ X_rest.T @ y_col
            y_hat     = X_rest @ betas
            ss_res    = np.sum((y_col - y_hat) ** 2)
            ss_tot    = np.sum((y_col - y_col.mean()) ** 2)
            r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
            vif       = 1.0 / (1.0 - r_squared) if r_squared < 1.0 else float("inf")
        except Exception:
            vif = float("nan")

        vif_val = float(vif) if np.isfinite(vif) else None
        results.append({
            "feature": feat,
            "vif": round(vif_val, 2) if vif_val is not None else None,
            "flag": (
                "HIGH_COLLINEARITY" if (vif_val is not None and vif_val > threshold)
                else "OK"
            ),
        })

    return sorted(results, key=lambda d: d["vif"] or 0, reverse=True)
