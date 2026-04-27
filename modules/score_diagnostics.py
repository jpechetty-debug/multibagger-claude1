# modules/score_diagnostics.py
"""
Sovereign AI — Score Diagnostics & Calibration Engine

Provides:
  - Score distribution analysis (deciles, sector breakdown)
  - Per-stock score explanation (top drivers, penalties, ceilings)
  - Calibration health report (graveyard detection, range utilization)
  - Cap reason counts
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_RUNTIME_DIR = _PROJECT_ROOT / "runtime"
_DB_PATH = str(_RUNTIME_DIR / "stocks.db")


def _get_connection():
    db_path = _DB_PATH
    if not Path(db_path).exists():
        alt = _PROJECT_ROOT / "stocks.db"
        if alt.exists():
            db_path = str(alt)
    conn = sqlite3.connect(db_path, timeout=5, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout=3000")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def get_score_distribution() -> dict[str, Any]:
    """
    Compute score distribution across the universe:
    - Deciles (0-10, 10-20, ..., 90-100)
    - Basic stats (mean, median, std, min, max)
    - Count at common "graveyard" values (59-61 range)
    """
    conn = _get_connection()
    try:
        rows = conn.execute("SELECT score FROM multibaggers WHERE score IS NOT NULL").fetchall()
        if not rows:
            return {"deciles": {}, "stats": {}, "graveyard_count": 0, "total": 0}

        scores = [float(r["score"]) for r in rows]
        scores_arr = np.array(scores)

        # Decile histogram
        deciles = {}
        for i in range(10):
            lo, hi = i * 10, (i + 1) * 10
            label = f"{lo}-{hi}"
            count = int(np.sum((scores_arr >= lo) & (scores_arr < hi)))
            deciles[label] = count
        # Handle exactly 100
        deciles["90-100"] = int(np.sum(scores_arr >= 90))

        # Graveyard detection (59-61 cluster)
        graveyard_count = int(np.sum((scores_arr >= 59) & (scores_arr <= 61)))

        # Top 5% threshold
        top5_threshold = float(np.percentile(scores_arr, 95))

        return {
            "deciles": deciles,
            "stats": {
                "mean": round(float(np.mean(scores_arr)), 2),
                "median": round(float(np.median(scores_arr)), 2),
                "std": round(float(np.std(scores_arr)), 2),
                "min": round(float(np.min(scores_arr)), 2),
                "max": round(float(np.max(scores_arr)), 2),
                "p5": round(float(np.percentile(scores_arr, 5)), 2),
                "p25": round(float(np.percentile(scores_arr, 25)), 2),
                "p75": round(float(np.percentile(scores_arr, 75)), 2),
                "p95": round(top5_threshold, 2),
            },
            "graveyard_count": graveyard_count,
            "graveyard_pct": round((graveyard_count / len(scores)) * 100, 1),
            "top5_threshold": round(top5_threshold, 2),
            "total": len(scores),
        }
    finally:
        conn.close()


def get_sector_distribution() -> dict[str, Any]:
    """Score ranges per sector with min/max/avg/median."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT sector, score FROM multibaggers WHERE score IS NOT NULL AND sector IS NOT NULL"
        ).fetchall()
        if not rows:
            return {"sectors": {}}

        sector_scores: dict[str, list[float]] = {}
        for r in rows:
            sector = r["sector"] or "Unknown"
            sector_scores.setdefault(sector, []).append(float(r["score"]))

        result = {}
        for sector, scores in sorted(sector_scores.items()):
            arr = np.array(scores)
            result[sector] = {
                "count": len(scores),
                "mean": round(float(np.mean(arr)), 1),
                "median": round(float(np.median(arr)), 1),
                "min": round(float(np.min(arr)), 1),
                "max": round(float(np.max(arr)), 1),
                "std": round(float(np.std(arr)), 1),
            }

        return {"sectors": result}
    finally:
        conn.close()


def get_score_explanation(symbol: str) -> dict[str, Any]:
    """
    Full score explanation for one stock:
    - top 3 positive drivers
    - top 3 penalties
    - active score ceilings
    - checklist pass/fail
    - data missingness
    - score delta from previous scan
    """
    conn = _get_connection()
    try:
        # Get stock data
        row = conn.execute(
            "SELECT * FROM multibaggers WHERE symbol = ?", (symbol,)
        ).fetchone()
        if not row:
            return {"error": f"Stock {symbol} not found"}

        stock = dict(row)
        score = stock.get("score", 0)

        # Build explanation from factor analysis
        positive_drivers = []
        penalties = []
        missing_factors = []

        # ROE analysis
        roe = stock.get("avg_roe_5y") or stock.get("roe")
        if roe is not None and roe > 15:
            positive_drivers.append({"factor": "Strong ROE", "value": f"{roe:.1f}%", "impact": "high"})
        elif roe is not None and roe < 5:
            penalties.append({"factor": "Weak ROE", "value": f"{roe:.1f}%", "impact": "high"})
        elif roe is None:
            missing_factors.append("ROE")

        # Sales growth analysis
        sg = stock.get("sales_cagr_5y") or stock.get("sales_growth")
        if sg is not None and sg > 15:
            positive_drivers.append({"factor": "Strong Revenue Growth", "value": f"{sg:.1f}%", "impact": "high"})
        elif sg is not None and sg < 0:
            penalties.append({"factor": "Revenue Decline", "value": f"{sg:.1f}%", "impact": "high"})
        elif sg is None:
            missing_factors.append("Sales Growth")

        # Valuation
        pe = stock.get("pe_ratio")
        if pe is not None and 0 < pe < 15:
            positive_drivers.append({"factor": "Attractive Valuation", "value": f"PE {pe:.1f}", "impact": "medium"})
        elif pe is not None and pe > 60:
            penalties.append({"factor": "Overvalued", "value": f"PE {pe:.1f}", "impact": "high"})
        elif pe is None or pe == 0:
            missing_factors.append("PE Ratio")

        # Debt
        de = stock.get("debt_equity")
        if de is not None and 0 <= de < 0.5:
            positive_drivers.append({"factor": "Low Debt", "value": f"D/E {de:.2f}", "impact": "medium"})
        elif de is not None and de > 2.0:
            penalties.append({"factor": "High Debt", "value": f"D/E {de:.2f}", "impact": "high"})
        elif de is None:
            missing_factors.append("Debt/Equity")

        # CFO/PAT
        cfo = stock.get("cfo_pat_ratio")
        if cfo is not None and cfo > 1.0:
            positive_drivers.append({"factor": "Strong Cash Generation", "value": f"CFO/PAT {cfo:.2f}", "impact": "medium"})
        elif cfo is not None and cfo < 0.5:
            penalties.append({"factor": "Weak Cash Quality", "value": f"CFO/PAT {cfo:.2f}", "impact": "medium"})
        elif cfo is None:
            missing_factors.append("CFO/PAT")

        # Promoter holding
        prom = stock.get("promoter_holding")
        if prom is not None and prom > 60:
            positive_drivers.append({"factor": "High Promoter Confidence", "value": f"{prom:.1f}%", "impact": "medium"})
        elif prom is not None and prom < 25:
            penalties.append({"factor": "Low Promoter Holding", "value": f"{prom:.1f}%", "impact": "medium"})

        # Pledge
        pledge = stock.get("pledge_pct")
        if pledge is not None and pledge > 10:
            penalties.append({"factor": "Significant Pledge", "value": f"{pledge:.1f}%", "impact": "high"})

        # Market cap
        mcap = stock.get("market_cap_cr")
        if mcap is None:
            missing_factors.append("Market Cap")

        # F-Score
        fscore = stock.get("f_score")
        if fscore is not None and fscore >= 7:
            positive_drivers.append({"factor": "High Piotroski Score", "value": f"{fscore}/9", "impact": "medium"})
        elif fscore is not None and fscore <= 3:
            penalties.append({"factor": "Low Piotroski Score", "value": f"{fscore}/9", "impact": "medium"})
        elif fscore is None:
            missing_factors.append("Piotroski F-Score")

        # Sort by impact weight
        impact_weight = {"high": 3, "medium": 2, "low": 1}
        positive_drivers.sort(key=lambda x: impact_weight.get(x["impact"], 0), reverse=True)
        penalties.sort(key=lambda x: impact_weight.get(x["impact"], 0), reverse=True)

        # Score change from previous scan
        score_delta = _get_score_delta(conn, symbol, score)

        # Data quality
        data_quality = stock.get("data_quality") or stock.get("data_confidence") or 0

        return {
            "symbol": symbol,
            "score": score,
            "sector": stock.get("sector", "Unknown"),
            "top_positive_drivers": positive_drivers[:3],
            "top_penalties": penalties[:3],
            "active_ceilings": _infer_active_ceilings(stock),
            "checklist_status": _build_checklist_status(stock),
            "missing_factors": missing_factors,
            "data_quality": round(float(data_quality), 1) if data_quality else 0,
            "score_delta": score_delta,
        }
    finally:
        conn.close()


def _get_score_delta(conn, symbol: str, current_score: float) -> dict[str, Any] | None:
    """Get score change from previous PIT snapshot."""
    try:
        rows = conn.execute(
            """SELECT score, as_of_date FROM fundamentals_pit
               WHERE symbol = ?
               ORDER BY as_of_date DESC LIMIT 2""",
            (symbol,),
        ).fetchall()

        if len(rows) < 2:
            return None

        prev_score = rows[1]["score"]
        if prev_score is None:
            return None

        delta = current_score - prev_score
        return {
            "previous_score": round(float(prev_score), 1),
            "delta": round(float(delta), 1),
            "previous_date": rows[1]["as_of_date"],
            "direction": "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT",
            "reason": _infer_delta_reason(delta, current_score, prev_score),
        }
    except Exception:
        return None


def _infer_delta_reason(delta: float, current: float, previous: float) -> str:
    abs_delta = abs(delta)
    if abs_delta < 1:
        return "Score effectively unchanged"
    if abs_delta < 5:
        return f"Minor {'improvement' if delta > 0 else 'decline'} in factor scores"
    if delta > 0:
        return "Significant improvement — likely fundamentals upgrade or new data"
    return "Significant decline — possible earnings miss or data degradation"


def _infer_active_ceilings(stock: dict) -> list[dict[str, Any]]:
    """Infer which score ceilings are likely active based on stock characteristics."""
    ceilings = []
    roe = stock.get("avg_roe_5y") or stock.get("roe") or 0
    if roe < 15:
        ceilings.append({"name": "ROE Decay Spline", "cap": round(50 + (roe / 15) * 50, 0), "active": True})
    sg = stock.get("sales_cagr_5y") or stock.get("sales_growth") or 0
    if sg < 10:
        ceilings.append({"name": "Growth Decay Spline", "cap": round(50 + (max(sg, -5) / 10) * 50, 0), "active": True})
    fscore = stock.get("f_score")
    if fscore is not None and fscore <= 4:
        ceilings.append({"name": "Quality Floor Spline", "cap": round(65 + fscore * 5.9, 0), "active": True})
    cfo = stock.get("cfo_pat_ratio") or 0
    if cfo < 0.8:
        ceilings.append({"name": "Cash Quality Spline", "cap": round(50 + (cfo / 0.8) * 50, 0), "active": True})
    return ceilings


def _build_checklist_status(stock: dict) -> dict[str, Any]:
    """Reconstruct checklist pass/fail from stock data."""
    checks = {}
    mcap = stock.get("market_cap_cr")
    checks["Market Cap > 1000 Cr"] = mcap is not None and mcap > 1000
    pe = stock.get("pe_ratio")
    checks["PE < 25"] = pe is not None and 0 < pe < 25
    roe = stock.get("avg_roe_5y") or stock.get("roe") or 0
    checks["ROE > 17%"] = roe > 17
    de = stock.get("debt_equity")
    checks["Debt/Equity < 1"] = de is not None and 0 <= de < 1.0
    cfo = stock.get("cfo_pat_ratio") or 0
    checks["CFO/PAT > 1"] = cfo > 1.0
    sg = stock.get("sales_cagr_5y") or stock.get("sales_growth") or 0
    checks["Sales Growth > 15%"] = sg > 15
    fscore = stock.get("f_score")
    checks["F-Score ≥ 6"] = fscore is not None and fscore >= 6
    prom = stock.get("promoter_holding") or 0
    checks["Promoter > 50%"] = prom > 50

    passed = sum(1 for v in checks.values() if v)
    return {
        "items": checks,
        "passed": passed,
        "total": len(checks),
        "grade": "A" if passed >= 7 else "B" if passed >= 5 else "C" if passed >= 3 else "D",
    }


def get_calibration_report() -> dict[str, Any]:
    """Overall calibration health: is the scoring engine producing meaningful differentiation?"""
    dist = get_score_distribution()
    sector = get_sector_distribution()

    stats = dist.get("stats", {})
    graveyard_pct = dist.get("graveyard_pct", 0)

    # Calibration quality indicators
    issues = []
    if graveyard_pct > 30:
        issues.append({
            "severity": "CRITICAL",
            "issue": f"{graveyard_pct}% of stocks score 59-61 — 'graveyard' clustering",
            "fix": "Score ceiling splines are converging. Spread min_cap values.",
        })
    if stats.get("std", 0) < 10:
        issues.append({
            "severity": "WARNING",
            "issue": f"Low score variance (σ={stats.get('std', 0)}). Scores lack differentiation.",
            "fix": "Increase weight spread or reduce ceiling convergence.",
        })
    if stats.get("max", 0) < 85:
        issues.append({
            "severity": "WARNING",
            "issue": f"No high-conviction picks (max={stats.get('max', 0)}). Top end is capped.",
            "fix": "Review checklist gate and bonus cap limits.",
        })

    above_90 = sum(v for k, v in dist.get("deciles", {}).items() if k.startswith("9"))
    total = dist.get("total", 1)
    top5_rarity = round((above_90 / max(total, 1)) * 100, 1)

    return {
        "distribution": dist,
        "sector_distribution": sector,
        "calibration_issues": issues,
        "top5_rarity_pct": top5_rarity,
        "effective_range": f"{stats.get('p5', 0)} — {stats.get('p95', 0)}",
        "health": "GOOD" if not issues else "NEEDS_ATTENTION" if len(issues) < 2 else "POOR",
        "timestamp": datetime.now().isoformat(),
    }
