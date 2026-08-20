from datetime import date
from pydantic import BaseModel, Field

class InvestmentThesis(BaseModel):
    """
    Structured investment thesis for a company, forcing quarterly reviews.
    """
    symbol: str
    created_date: date
    expected_cagr: float
    risks: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    disconfirming_evidence: list[str] = Field(default_factory=list)
    last_reviewed_date: date
