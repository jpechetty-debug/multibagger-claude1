# app_routes/freshness.py
"""
Sovereign AI — Data Freshness & Quality API Routes

Exposes:
  GET /api/data-freshness     — freshness badge data
  GET /api/provider-health    — yfinance/NSE/pnsea success rates
  GET /api/universe-quality   — staleness alert for the universe
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from modules.data_freshness import (
    get_freshness_report,
    get_provider_health,
    get_universe_quality,
)

router = APIRouter()


@router.get("/api/data-freshness")
async def data_freshness():
    """Return freshness badge data: status, latest_as_of_date, age_days, source, data_quality."""
    report = get_freshness_report()
    return asdict(report)


@router.get("/api/provider-health")
async def provider_health():
    """Return yfinance/NSE/pnsea success rates and health status."""
    providers = get_provider_health()
    return {"providers": [asdict(p) for p in providers]}


@router.get("/api/universe-quality")
async def universe_quality():
    """Return universe staleness metrics and alert status."""
    quality = get_universe_quality()
    return asdict(quality)
