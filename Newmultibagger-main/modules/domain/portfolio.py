from typing import List
from pydantic import BaseModel
from .position import Position

class Portfolio(BaseModel):
    """
    Represents a collection of positions.
    """
    name: str
    positions: list[Position] = []
    cash: float = 0.0
