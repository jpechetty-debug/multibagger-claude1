# modules/stress_test.py
"""
Sovereign Adversarial Stress Test Harness
==========================================
Implements the full scenario replay required for Risk Containment gate evidence:
  - Gap-down shock (overnight price gap)
  - Slippage expansion (liquidity crisis fill degradation)
  - Correlation spike (crisis-regime diversification collapse)
  - VIX regime flip (volatility regime transition)

Each scenario runs independently and returns a structured result so the
RiskGovernor can decide whether to activate the kill switch or tighten
position limits before executing new orders.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

try:
    from core.observability.logger import get_logger
    _log = get_logger("modules.stress_test")
except Exception:
    import logging
    _log = logging.getLogger("modules.stress_test")


# ── Scenario result ───────────────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    scenario:          str
    triggered:         bool
    severity:          str          # "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    portfolio_impact:  float        # estimated % PnL impact
    breach_details:    dict         = field(default_factory=dict)
    recommendation:    str          = ""

    def to_dict(self) -> dict:
        return {
            "scenario":         self.scenario,
            "triggered":        self.triggered,
            "severity":         self.severity,
            "portfolio_impact": round(self.portfolio_impact, 4),
            "breach_details":   self.breach_details,
            "recommendation":   self.recommendation,
        }


# ── Scenario 1: Gap-down shock ────────────────────────────────────────────────

def simulate_gap_down(
    portfolio: pd.DataFrame,
    gap_pct: float = 0.10,
    affected_fraction: float = 0.30,
) -> ScenarioResult:
    """Model an overnight gap-down event affecting a fraction of positions.

    Args:
        portfolio: DataFrame with columns [symbol, position_value, stop_loss].
        gap_pct: Overnight gap magnitude as a fraction (e.g. 0.10 = 10% gap).
        affected_fraction: Fraction of portfolio positions gapped (default 30%).

    Returns:
        ScenarioResult with portfolio_impact and stop_loss breach details.
    """
    if portfolio.empty:
        return ScenarioResult("gap_down", False, "LOW", 0.0,
                              recommendation="No open positions to stress-test.")

    total_value = portfolio["position_value"].sum()
    affected    = portfolio.sample(
        frac=min(affected_fraction, 1.0), random_state=42
    )
    gap_loss    = affected["position_value"].sum() * gap_pct

    # Check which positions gap through their stop_loss
    breaches = []
    if "stop_loss" in portfolio.columns and "entry_price" in portfolio.columns:
        for _, row in affected.iterrows():
            gap_price = row.get("entry_price", 100) * (1 - gap_pct)
            if gap_price < row.get("stop_loss", 0):
                breaches.append({
                    "symbol":     row.get("symbol", "?"),
                    "gap_price":  round(gap_price, 2),
                    "stop_loss":  row.get("stop_loss", 0),
                    "slippage":   round(row.get("stop_loss", 0) - gap_price, 2),
                })

    impact_pct = gap_loss / total_value if total_value > 0 else 0.0
    severity   = (
        "CRITICAL" if impact_pct > 0.15 else
        "HIGH"     if impact_pct > 0.08 else
        "MEDIUM"   if impact_pct > 0.03 else "LOW"
    )

    _log.info(
        "Gap-down scenario",
        gap_pct=gap_pct,
        impact_pct=round(impact_pct, 4),
        breaches=len(breaches),
        severity=severity,
    )

    return ScenarioResult(
        scenario="gap_down",
        triggered=impact_pct > 0.05,
        severity=severity,
        portfolio_impact=-impact_pct,
        breach_details={"stop_loss_breaches": breaches, "affected_positions": len(affected)},
        recommendation=(
            "Activate kill switch — gap exceeds 15% drawdown threshold."
            if severity == "CRITICAL"
            else "Tighten stop losses on affected positions." if severity == "HIGH"
            else "Monitor closely."
        ),
    )


# ── Scenario 2: Slippage expansion ───────────────────────────────────────────

def simulate_slippage_expansion(
    orders: list[dict],
    normal_slippage_bps: float = 30.0,
    crisis_slippage_multiplier: float = 5.0,
) -> ScenarioResult:
    """Model slippage expansion during a liquidity crisis.

    In normal markets, slippage is ~30 bps round-trip for mid-cap stocks.
    During a crisis, market impact and bid-ask spread widen to 5–10× normal.

    Args:
        orders: List of dicts with keys [symbol, size_cr, direction].
        normal_slippage_bps: Baseline round-trip slippage in basis points.
        crisis_slippage_multiplier: How much slippage expands in crisis.

    Returns:
        ScenarioResult with total execution cost uplift.
    """
    if not orders:
        return ScenarioResult("slippage_expansion", False, "LOW", 0.0)

    crisis_slippage_bps = normal_slippage_bps * crisis_slippage_multiplier
    total_order_value_cr = sum(o.get("size_cr", 0) for o in orders)
    normal_cost_cr  = total_order_value_cr * (normal_slippage_bps  / 10_000)
    crisis_cost_cr  = total_order_value_cr * (crisis_slippage_bps  / 10_000)
    uplift_cr       = crisis_cost_cr - normal_cost_cr

    uplift_pct      = uplift_cr / total_order_value_cr if total_order_value_cr > 0 else 0.0
    severity        = (
        "CRITICAL" if crisis_slippage_bps > 300 else
        "HIGH"     if crisis_slippage_bps > 150 else
        "MEDIUM"   if crisis_slippage_bps > 75  else "LOW"
    )

    _log.info(
        "Slippage expansion scenario",
        normal_bps=normal_slippage_bps,
        crisis_bps=crisis_slippage_bps,
        uplift_cr=round(uplift_cr, 2),
        severity=severity,
    )

    return ScenarioResult(
        scenario="slippage_expansion",
        triggered=crisis_slippage_bps > 100,
        severity=severity,
        portfolio_impact=-uplift_pct,
        breach_details={
            "normal_slippage_bps":  normal_slippage_bps,
            "crisis_slippage_bps":  crisis_slippage_bps,
            "multiplier":           crisis_slippage_multiplier,
            "uplift_cost_cr":       round(uplift_cr, 2),
            "total_orders_cr":      round(total_order_value_cr, 2),
        },
        recommendation=(
            "Suspend new orders — execution costs exceed 3% of order value."
            if severity == "CRITICAL"
            else "Reduce order sizes or defer discretionary trades."
        ),
    )


# ── Scenario 3: Correlation spike ────────────────────────────────────────────

def simulate_correlation_spike(
    returns_matrix: pd.DataFrame,
    normal_avg_corr: float = 0.30,
    crisis_corr_threshold: float = 0.75,
) -> ScenarioResult:
    """Model diversification collapse during a correlation spike.

    In a crisis, inter-stock correlations surge toward 1.0 as investors
    sell everything indiscriminately.  This scenario estimates how much
    of the portfolio's apparent diversification benefit evaporates.

    Args:
        returns_matrix: Wide DataFrame of daily returns (symbols as columns).
        normal_avg_corr: Expected average pairwise correlation in normal markets.
        crisis_corr_threshold: Correlation level above which diversification fails.

    Returns:
        ScenarioResult with diversification ratio and concentration risk.
    """
    if returns_matrix.empty or returns_matrix.shape[1] < 2:
        return ScenarioResult("correlation_spike", False, "LOW", 0.0)

    corr_matrix   = returns_matrix.corr()
    n             = len(corr_matrix)
    upper_mask    = np.triu(np.ones((n, n), dtype=bool), k=1)
    avg_corr      = float(corr_matrix.values[upper_mask].mean())
    crisis_corr   = min(avg_corr * (crisis_corr_threshold / max(normal_avg_corr, 0.01)), 0.95)

    # Effective N (diversification ratio) = 1 / (1 + (N-1)*corr)
    n_positions   = returns_matrix.shape[1]
    normal_eff_n  = n_positions / (1 + (n_positions - 1) * normal_avg_corr)
    crisis_eff_n  = n_positions / (1 + (n_positions - 1) * crisis_corr)
    div_loss_pct  = (normal_eff_n - crisis_eff_n) / normal_eff_n

    severity      = (
        "CRITICAL" if crisis_corr > 0.85 else
        "HIGH"     if crisis_corr > 0.70 else
        "MEDIUM"   if crisis_corr > 0.55 else "LOW"
    )

    _log.info(
        "Correlation spike scenario",
        avg_corr=round(avg_corr, 3),
        crisis_corr=round(crisis_corr, 3),
        normal_eff_n=round(normal_eff_n, 1),
        crisis_eff_n=round(crisis_eff_n, 1),
        severity=severity,
    )

    return ScenarioResult(
        scenario="correlation_spike",
        triggered=crisis_corr > crisis_corr_threshold,
        severity=severity,
        portfolio_impact=-div_loss_pct * 0.5,  # halved: not all corr loss = PnL loss
        breach_details={
            "observed_avg_corr":  round(avg_corr, 3),
            "crisis_corr":        round(crisis_corr, 3),
            "normal_effective_n": round(normal_eff_n, 1),
            "crisis_effective_n": round(crisis_eff_n, 1),
            "diversification_loss_pct": round(div_loss_pct * 100, 1),
        },
        recommendation=(
            "Reduce portfolio to core high-conviction names — diversification benefit eliminated."
            if severity == "CRITICAL"
            else "Consider sector concentration limits." if severity == "HIGH"
            else "Portfolio diversification holding."
        ),
    )


# ── Scenario 4: VIX regime flip ──────────────────────────────────────────────

def simulate_vix_regime_flip(
    current_vix: float,
    portfolio_beta: float = 1.0,
    portfolio_value_cr: float = 100.0,
    vix_spike_multiple: float = 2.5,
) -> ScenarioResult:
    """Model a sudden VIX regime flip (e.g. VIX doubles in a single session).

    Estimates expected portfolio drawdown using the empirical relationship
    between VIX changes and equity market returns.

    Args:
        current_vix: Current VIX level.
        portfolio_beta: Portfolio beta relative to Nifty 50 (default 1.0).
        portfolio_value_cr: Portfolio AUM in crores.
        vix_spike_multiple: How much VIX is assumed to spike (default 2.5×).

    Returns:
        ScenarioResult with expected drawdown and kill switch recommendation.
    """
    stressed_vix    = current_vix * vix_spike_multiple
    # Empirical rule: VIX doubling ≈ 8–12% equity drawdown for beta=1 portfolio
    base_drawdown   = 0.10 * math.log(vix_spike_multiple) / math.log(2)
    portfolio_dd    = base_drawdown * portfolio_beta
    loss_cr         = portfolio_value_cr * portfolio_dd

    kill_switch_vix = float(__import__("os").getenv("VIX_KILL_SWITCH", 25))
    triggered       = stressed_vix >= kill_switch_vix

    severity        = (
        "CRITICAL" if stressed_vix > 60  else
        "HIGH"     if stressed_vix > 40  else
        "MEDIUM"   if stressed_vix > 30  else "LOW"
    )

    _log.info(
        "VIX regime flip scenario",
        current_vix=current_vix,
        stressed_vix=round(stressed_vix, 1),
        kill_switch_threshold=kill_switch_vix,
        triggered=triggered,
        portfolio_dd_pct=round(portfolio_dd * 100, 2),
        severity=severity,
    )

    return ScenarioResult(
        scenario="vix_regime_flip",
        triggered=triggered,
        severity=severity,
        portfolio_impact=-portfolio_dd,
        breach_details={
            "current_vix":       current_vix,
            "stressed_vix":      round(stressed_vix, 1),
            "kill_switch_vix":   kill_switch_vix,
            "portfolio_beta":    portfolio_beta,
            "expected_loss_cr":  round(loss_cr, 2),
            "drawdown_pct":      round(portfolio_dd * 100, 2),
        },
        recommendation=(
            f"ACTIVATE KILL SWITCH — stressed VIX {stressed_vix:.0f} exceeds threshold {kill_switch_vix}."
            if triggered
            else f"Monitor — stressed VIX {stressed_vix:.0f} approaches threshold."
        ),
    )


# ── Composite replay ──────────────────────────────────────────────────────────

def run_full_scenario_replay(
    portfolio: pd.DataFrame | None = None,
    orders: list[dict] | None = None,
    returns_matrix: pd.DataFrame | None = None,
    current_vix: float = 18.0,
    portfolio_beta: float = 1.0,
    portfolio_value_cr: float = 100.0,
) -> dict[str, Any]:
    """Run all 4 adversarial scenarios in one call.

    Returns a dict with results for each scenario plus an overall
    ``max_severity`` and ``any_critical`` flag for the RiskGovernor.
    """
    results = {
        "gap":         simulate_gap_down(portfolio or pd.DataFrame()).to_dict(),
        "slippage":    simulate_slippage_expansion(orders or []).to_dict(),
        "correlation": simulate_correlation_spike(returns_matrix or pd.DataFrame()).to_dict(),
        "vix":         simulate_vix_regime_flip(current_vix, portfolio_beta, portfolio_value_cr).to_dict(),
    }

    severities  = [r["severity"] for r in results.values()]
    rank        = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    max_sev     = max(severities, key=lambda s: rank.get(s, 0))

    return {
        "scenarios":    results,
        "max_severity": max_sev,
        "any_critical": max_sev == "CRITICAL",
        "any_triggered":any(r["triggered"] for r in results.values()),
    }
