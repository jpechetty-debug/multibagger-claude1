from __future__ import annotations
from datetime import date
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class CompanySnapshot(BaseModel):
    """
    Canonical representation of a Company at an exact point in time.
    This is the core data structure of the Sovereign Research Terminal.
    Downstream scoring and analytic engines consume this snapshot,
    ensuring no lookahead bias can leak through.
    """
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(..., min_length=1, description="The ticker symbol of the company.")
    as_of_date: date = Field(..., description="The exact date this snapshot represents. All data must be known as of this date.")
    
    # Raw Data Modules
    financials: dict[str, Any] = Field(default_factory=dict, description="Financial statements available exactly on or before as_of_date.")
    prices: dict[str, Any] = Field(default_factory=dict, description="Price history available on or before as_of_date.")
    features: dict[str, Any] = Field(default_factory=dict, description="Pre-computed technical/fundamental features as of as_of_date.")
    
    # Computed Scores
    scores: dict[str, float] = Field(default_factory=dict, description="Domain scores (e.g. Quality, Momentum, Compounder) calculated for this snapshot.")

    @property
    def is_stale(self) -> bool:
        """Helper to determine if the snapshot is missing critical recency data."""
        return not bool(self.financials) or not bool(self.prices)
