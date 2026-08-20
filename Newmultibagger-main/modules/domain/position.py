from pydantic import BaseModel

class Position(BaseModel):
    """
    Represents a holding in a portfolio.
    """
    symbol: str
    quantity: float
    average_cost: float
