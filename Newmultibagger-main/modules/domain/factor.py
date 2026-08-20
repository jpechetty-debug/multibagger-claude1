from pydantic import BaseModel

class Factor(BaseModel):
    """
    Represents a single raw factor (e.g. 10-year Revenue CAGR).
    """
    name: str
    value: float
