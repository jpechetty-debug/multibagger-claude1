from pydantic import BaseModel

class Security(BaseModel):
    """
    Represents a tradable instrument.
    """
    symbol: str
    asset_class: str = "equity"
