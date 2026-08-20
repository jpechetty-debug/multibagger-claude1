from pydantic import BaseModel

class Score(BaseModel):
    """
    Represents an aggregated score (e.g. Quality Score, Compounder Score).
    """
    name: str
    value: float
    components: dict[str, float]
