"""
Feature Leakage Audit
---------------------
Systematically audits every ML feature for temporal validity and
suspiciously high predictive power (leakage signal).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from modules.hybrid_scoring import FEATURES

# Features with known publication lags (fundamentals) vs market-derived
_FUNDAMENTAL_FEATURES = {"score", "sales_cagr_5y", "avg_roe_5y", "pe_ratio",
                         "debt_equity", "cfo_pat_ratio", "market_cap_cr", "roce"}
_MOMENTUM_FEATURES = {"ret_1m", "ret_3m", "ret_6m", "vol_breakout", "dist_from_52w_high"}

SPEARMAN_LEAK_THRESHOLD = 0.4


@dataclass
class FeatureVerdict:
    feature: str
    spearman_r: float | None
    classification: str  # SAFE, NEEDS_REVIEW, LEAKING
    reason: str = ""


@dataclass
class LeakageReport:
    verdicts: list[FeatureVerdict] = field(default_factory=list)
    leaking_count: int = 0
    review_count: int = 0

    @property
    def has_leaks(self) -> bool:
        return self.leaking_count > 0


def audit_features(
    pit_df: pd.DataFrame,
    forward_return_col: str = "forward_return",
) -> LeakageReport:
    """Audit each feature for leakage against forward returns.

    Args:
        pit_df: DataFrame with FEATURES columns and ``forward_return_col``.
        forward_return_col: Name of the target column.

    Returns:
        LeakageReport with per-feature verdicts.
    """
    report = LeakageReport()
    if forward_return_col not in pit_df.columns:
        return report

    y = pd.to_numeric(pit_df[forward_return_col], errors="coerce")

    for feat in FEATURES:
        if feat not in pit_df.columns:
            report.verdicts.append(
                FeatureVerdict(feat, None, "SAFE", "column missing, filled with 0")
            )
            continue

        x = pd.to_numeric(pit_df[feat], errors="coerce")
        valid = x.notna() & y.notna()
        if valid.sum() < 5:
            report.verdicts.append(
                FeatureVerdict(feat, None, "SAFE", "too few observations")
            )
            continue

        r = x[valid].corr(y[valid], method="spearman")
        r = float(r) if np.isfinite(r) else 0.0

        if abs(r) > SPEARMAN_LEAK_THRESHOLD:
            if feat in _FUNDAMENTAL_FEATURES:
                classification = "NEEDS_REVIEW"
                reason = f"|r|={abs(r):.3f} > {SPEARMAN_LEAK_THRESHOLD} but has known lag"
                report.review_count += 1
            else:
                classification = "LEAKING"
                reason = f"|r|={abs(r):.3f} > {SPEARMAN_LEAK_THRESHOLD}, no documented lag"
                report.leaking_count += 1
        elif feat in _MOMENTUM_FEATURES and abs(r) > 0.15:
            classification = "NEEDS_REVIEW"
            reason = f"momentum feature with significant correlation: |r|={abs(r):.3f} > 0.15 — verify price date <= as_of_date"
            report.review_count += 1
        else:
            classification = "SAFE"
            reason = f"|r|={abs(r):.3f}"

        report.verdicts.append(FeatureVerdict(feat, r, classification, reason))

    return report


def validate_momentum_returns(
    pit_df: pd.DataFrame,
    tolerance: float = 0.05,
) -> list[dict]:
    """Validate momentum return features against PIT price if available.

    Returns list of dicts describing mismatches.
    """
    issues: list[dict] = []
    if "price" not in pit_df.columns or "as_of_date" not in pit_df.columns:
        return issues

    # Group by symbol and check ret_1m reconstruction
    for sym, group in pit_df.groupby("symbol"):
        group = group.sort_values("as_of_date").copy()
        if len(group) < 2 or "ret_1m" not in group.columns:
            continue
        prices = pd.to_numeric(group["price"], errors="coerce")
        reported_ret = pd.to_numeric(group["ret_1m"], errors="coerce")
        computed_ret = prices.pct_change() * 100  # percent

        diff = (reported_ret - computed_ret).dropna().abs()
        bad = diff[diff > tolerance * 100]  # tolerance as pct
        if not bad.empty:
            issues.append({
                "symbol": sym,
                "mismatched_rows": int(len(bad)),
                "max_diff_pct": float(bad.max()),
            })
    return issues
