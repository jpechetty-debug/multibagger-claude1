# modules/adapters/base.py
from abc import ABC, abstractmethod
from typing import Any


class DataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        pass
