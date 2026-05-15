from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    latency_reference: str


class SwarmStatusResponse(BaseModel):
    symbol: str
    status: Literal["mock", "analyzed", "pending"]
    consensus: str | None = None
    report_ready: bool | None = None


class SwarmReportResponse(BaseModel):
    symbol: str
    report: str


class NewsSignalResponse(BaseModel):
    symbol: str
    sentiment_score: float
    alignment: str
    headline_count: int
    headlines: list[str] = Field(default_factory=list)
    model_config = {"extra": "allow"}


class MarketCalendarResponse(BaseModel):
    valid_trading_days: list[str]


class MarkdownReportResponse(BaseModel):
    content: str


class PerformanceResponse(BaseModel):
    strategy: float
    benchmark: float
    alpha: float
    win_rate: float
    avg_hold: str


class RegimeStatusResponse(BaseModel):
    regime: str
    vix: float
    vix_threshold: float
    momentum_accel: float
    votes: dict[str, Any]
    is_forced: bool
    details: dict[str, Any]
    timestamp: str
    stale: bool | None = None
    error: str | None = None
