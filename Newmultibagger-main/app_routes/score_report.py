# app_routes/score_report.py
"""
Sovereign AI — Score Distribution & Calibration API Routes

Exposes:
  GET /api/score-distribution     — decile breakdown, sector distribution, cap reasons
  GET /api/score-explain/{symbol} — full score explanation for one stock
  GET /api/calibration-report     — overall calibration health
"""

from __future__ import annotations

from fastapi import APIRouter

from modules.score_diagnostics import (
    get_calibration_report,
    get_score_distribution,
    get_score_explanation,
    get_sector_distribution,
)

router = APIRouter()


@router.get("/api/score-distribution")
async def score_distribution():
    """Return decile breakdown, sector distribution, and cap reason counts."""
    from modules.dependencies import _json_safe_clean

    dist = get_score_distribution()
    sectors = get_sector_distribution()
    return _json_safe_clean({**dist, "sector_breakdown": sectors.get("sectors", {})})


@router.get("/api/score-explain/{symbol}")
async def score_explain(symbol: str):
    """Return full score explanation for one stock."""
    from modules.dependencies import _json_safe_clean

    if not symbol.endswith(".NS") and not symbol.endswith(".BO"):
        symbol += ".NS"
    return _json_safe_clean(get_score_explanation(symbol))


@router.get("/api/calibration-report")
async def calibration_report():
    """Return overall calibration health report."""
    from modules.dependencies import _json_safe_clean

    return _json_safe_clean(get_calibration_report())
