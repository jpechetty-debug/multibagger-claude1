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


class MultibaggerOut(BaseModel):
    symbol: str
    price: float | None = None
    sector: str | None = None
    score: float | None = None
    f_score: int | None = None
    rating: str | None = None
    buy_below: float | None = None
    stop_loss: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    sales_growth: float | None = None
    roe: float | None = None
    peg_ratio: float | None = None
    debt_equity: float | None = None
    rsi: float | None = None
    smart_money: float | None = None
    market_cap_cr: float | None = None
    cfo_pat_ratio: float | None = None
    sales_cagr_5y: float | None = None
    avg_roe_5y: float | None = None
    pe_ratio: float | None = None
    down_from_52w: float | None = None
    rs_rating: float | None = None
    earnings_accel: int | None = None
    sector_leader: int | None = None
    graham_number: float | None = None
    value_gap: float | None = None
    technical_signal: str | None = None
    analyst_rating: str | None = None
    analyst_upside: float | None = None
    promoter_holding: float | None = None
    inst_holding: float | None = None
    atr: float | None = None
    stop_loss_atr: float | None = None
    max_qty_1l: float | None = None
    as_of_date: str | None = None
    last_audited: str | None = None
    updated_at: str | None = None
    conviction_score: float | None = None
    conviction_boost: float | None = None
    institutional_interest: int | None = None
    super_investors: str | None = None
    backtest_cagr: float | None = None
    backtest_win_rate: float | None = None
    backtest_max_dd: float | None = None
    backtest_sharpe: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    pledge_pct: float | None = None
    piotroski_score: int | None = None
    data_quality: float | None = None
    data_confidence: float | None = None
    data_quality_flags: str | None = None
    liquidity_score: float | None = None
    trust_gate_pass: bool | None = None
    trust_gate_reasons: list[str] | None = None

    model_config = {"extra": "allow", "from_attributes": True}
