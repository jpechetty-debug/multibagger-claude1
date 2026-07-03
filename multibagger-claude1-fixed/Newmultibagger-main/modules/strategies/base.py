from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):
    """
    Base Protocol for Sovereign AI Quant Strategies.
    """
    def __init__(self, db_path: str = "stocks.db"):
        self.db_path = db_path
        self.universe: pd.DataFrame = pd.DataFrame()
        self.candidates: list[dict] = []

    @abstractmethod
    def load_universe(self) -> None:
        """
        Loads and prepares the initial universe of stocks for the strategy.
        Should populate self.universe.
        """

    @abstractmethod
    def generate_proposals(self, top_n: int = 20) -> list[dict]:
        """
        Runs filters and generation logic against the universe.
        Returns a list of proposal dictionaries.
        """
