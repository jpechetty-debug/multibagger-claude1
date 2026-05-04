# modules/models.py

from pydantic import BaseModel, ConfigDict, Field


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
    model_config = ConfigDict(extra="allow")  # Allow extra fields for dynamism

    Symbol: str
    Price: float | None = None
    PE_Ratio: float | None = None
    ROE_pct: float | None = Field(alias="ROE%", default=None)
    Debt_Equity: float | None = None
    Sales_Growth_TTM_pct: float | None = Field(alias="Sales_Growth_TTM%", default=None)
    CFO_PAT_Ratio: float | None = None
    F_Score: int | None = None
    Market_Cap_Cr: float | None = None
    Sector: str | None = "Unknown"
    Industry: str | None = "Unknown"
    Data_Source: str = "unknown"

    # Metadata and Flags
    _dq_flags: dict[str, bool] | None = None
    _fetch_error: str | None = None

    # Ensure ROE% and other aliases are handled correctly
    def model_dump(self, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)


class ScoringResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_score: float
    factors: dict[str, float] | None = None
    audit_trail: list[str] | None = None
    error: str | None = None
