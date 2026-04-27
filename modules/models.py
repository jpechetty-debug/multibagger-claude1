# modules/models.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any, List

class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1)
    side: str = Field(description="BUY or SELL")
    quantity: int = Field(default=1, ge=1)
    price: float = Field(gt=0)
    score: float = 0.0
    reason: str = "MANUAL"
    current_vix: Optional[float] = None
    drawdown_rate_weekly: Optional[float] = None
    portfolio_correlation: Optional[float] = None
    projected_var_pct: Optional[float] = None
    max_var_pct: float = 20.0

class StockDataPayload(BaseModel):
    model_config = ConfigDict(extra='allow') # Allow extra fields for dynamism
    
    Symbol: str
    Price: Optional[float] = None
    PE_Ratio: Optional[float] = None
    ROE_pct: Optional[float] = Field(alias="ROE%", default=None)
    Debt_Equity: Optional[float] = None
    Sales_Growth_TTM_pct: Optional[float] = Field(alias="Sales_Growth_TTM%", default=None)
    CFO_PAT_Ratio: Optional[float] = None
    F_Score: Optional[int] = None
    Market_Cap_Cr: Optional[float] = None
    Sector: Optional[str] = "Unknown"
    Industry: Optional[str] = "Unknown"
    Data_Source: str = "unknown"
    
    # Metadata and Flags
    _dq_flags: Optional[Dict[str, bool]] = None
    _fetch_error: Optional[str] = None
    
    # Ensure ROE% and other aliases are handled correctly
    def model_dump(self, **kwargs):
        kwargs.setdefault('by_alias', True)
        return super().model_dump(**kwargs)
