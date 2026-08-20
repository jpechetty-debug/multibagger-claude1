# modules/models.py
"""
Sovereign AI — Pydantic Data Models

Central ingestion boundary for all stock data entering the system.
Scale-ambiguous fields are normalized here at the edge so downstream
code never has to guess whether ROE is 0.15 or 15.0.
"""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.observability.logger import get_logger

_log = get_logger("modules.models")


def _normalize_fraction_to_pct(value: float | None, field_name: str) -> float | None:
    """Convert fraction-scale values to percent if they look like fractions.

    Note: Values exactly equal to 1.0 or -1.0 are treated as fractions and scaled to
    100.0% or -100.0%. This ambiguity assumes 1% is rare compared to 100%.
    """
    if value is None:
        return None
    if not math.isfinite(value):
        return None
    # Values in [-1, 1] are almost certainly fractions (0.15 = 15%)
    # Exception: values that are exactly 0 stay 0
    if value == 0:
        return 0.0
    if -1.0 <= value <= 1.0:
        return round(value * 100, 2)
    return round(value, 2)


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1)
    side: str = Field(description="BUY or SELL")
    quantity: int = Field(default=1, ge=1)
    price: float = Field(gt=0)
    score: float = 0.0
    reason: str = "MANUAL"
    current_vix: float | None = None
    drawdown_rate_weekly: float | None = None
    portfolio_correlation: float | None = None
    projected_var_pct: float | None = None
    max_var_pct: float = 20.0


class StockDataPayload(BaseModel):
    """Ingestion model for stock data from upstream providers.

    Unknown fields are rejected (extra='forbid') to prevent
    malformed data from leaking into the scoring engine.
    """

    model_config = ConfigDict(extra="allow")

    Symbol: str
    Price: float | None = None
    PE_Ratio: float | None = None
    ROE_pct: float | None = Field(alias="ROE%", default=None)
    Debt_Equity: float | None = None
    Sales_Growth_TTM_pct: float | None = Field(alias="Sales_Growth_TTM%", default=None)
    Sales_Growth_5Y_pct: float | None = Field(alias="Sales_Growth_5Y%", default=None)
    EPS_Growth_pct: float | None = Field(alias="EPS_Growth%", default=None)
    CFO_PAT_Ratio: float | None = None
    F_Score: int | None = None
    F_Score_Max: int | None = None
    Market_Cap_Cr: float | None = None
    Sector: str | None = "Unknown"
    Industry: str | None = "Unknown"
    Data_Source: str = "unknown"

    Promoter_Holding_pct: float | None = Field(alias="Promoter_Holding%", default=None)
    Inst_Holding_pct: float | None = Field(alias="Inst_Holding%", default=None)
    Pledge_Pct: float | None = None

    # Fetch Validity fields
    History_Bars_1Y: int | None = None
    Price_Age_Days: int | None = None
    Last_Price_Date: str | None = None
    Quarter_End: str | None = None
    As_Of_Date: str | None = None

    # Sprint 1: Compounding Lens fields
    Revenue_CAGR_3Y: float | None = None
    Revenue_CAGR_5Y: float | None = None
    PAT_CAGR_3Y: float | None = None
    PAT_CAGR_5Y: float | None = None
    EPS_CAGR_3Y: float | None = None
    EPS_CAGR_5Y: float | None = None
    CAGR_Consistency: str | None = None
    Dividend_Yield: float | None = None
    Dividend_Payout: float | None = None
    Cap_Category: str | None = None

    # ── Scale normalization validators ──────────────────────────────────

    @model_validator(mode="before")
    @classmethod
    def _warn_on_extra(cls, data: dict) -> dict:
        if not isinstance(data, dict):
            return data

        allowed_keys = set()
        for field_name, field_def in cls.model_fields.items():
            allowed_keys.add(field_name)
            if field_def.alias:
                allowed_keys.add(field_def.alias)

        extra_keys = set(data.keys()) - allowed_keys
        if extra_keys:
            symbol = data.get("Symbol", "Unknown")
            _log.warning(f"StockDataPayload for {symbol} received unknown fields: {extra_keys}")

        return data

    @field_validator("ROE_pct", mode="before")
    @classmethod
    def _normalize_roe(cls, v: float | None) -> float | None:
        return _normalize_fraction_to_pct(v, "ROE%")

    @field_validator("Sales_Growth_TTM_pct", mode="before")
    @classmethod
    def _normalize_sales_growth(cls, v: float | None) -> float | None:
        return _normalize_fraction_to_pct(v, "Sales_Growth_TTM%")

    @field_validator("Sales_Growth_5Y_pct", mode="before")
    @classmethod
    def _normalize_sales_growth_5y(cls, v: float | None) -> float | None:
        return _normalize_fraction_to_pct(v, "Sales_Growth_5Y%")

    @field_validator("EPS_Growth_pct", mode="before")
    @classmethod
    def _normalize_eps_growth(cls, v: float | None) -> float | None:
        return _normalize_fraction_to_pct(v, "EPS_Growth%")

    @field_validator("Dividend_Yield", mode="before")
    @classmethod
    def _normalize_dividend_yield(cls, v: float | None) -> float | None:
        result = _normalize_fraction_to_pct(v, "Dividend_Yield")
        # Sanity cap: no Indian stock yields > 25% realistically
        if result is not None and result > 25.0:
            return round(result / 100, 2)
        return result

    @field_validator("Dividend_Payout", mode="before")
    @classmethod
    def _normalize_dividend_payout(cls, v: float | None) -> float | None:
        result = _normalize_fraction_to_pct(v, "Dividend_Payout")
        if result is not None:
            return min(result, 200.0)
        return result

    @field_validator("PE_Ratio", mode="before")
    @classmethod
    def _clamp_pe(cls, v: float | None) -> float | None:
        if v is None:
            return None
        try:
            val = float(v)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(val):
            return None
        return max(-100.0, min(1000.0, val))

    @field_validator("Debt_Equity", mode="before")
    @classmethod
    def _clamp_debt_equity(cls, v: float | None) -> float | None:
        if v is None:
            return None
        try:
            val = float(v)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(val):
            return None
        return max(0.0, min(50.0, val))

    @property
    def data_quality_score(self) -> int:
        """Count of non-null key fields as a 0-100 score."""
        key_fields = [
            self.Price,
            self.PE_Ratio,
            self.ROE_pct,
            self.Debt_Equity,
            self.Sales_Growth_TTM_pct,
            self.CFO_PAT_Ratio,
            self.F_Score,
            self.Market_Cap_Cr,
        ]
        non_null = sum(1 for f in key_fields if f is not None)
        return round((non_null / len(key_fields)) * 100)

    @classmethod
    def clean_dict(cls, data: dict) -> dict:
        """Filter input dict keys to only allow fields or field aliases defined on this model."""
        allowed_keys = set()
        for field_name, field_def in cls.model_fields.items():
            allowed_keys.add(field_name)
            if field_def.alias:
                allowed_keys.add(field_def.alias)
        return {k: v for k, v in data.items() if k in allowed_keys}

    def model_dump(self, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)


class ScoringResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_score: float
    factors: dict[str, float] | None = None
    audit_trail: list[str] | None = None
    error: str | None = None
