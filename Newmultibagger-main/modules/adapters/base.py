# modules/adapters/base.py
from modules.structured_logger import SovereignLogger
from abc import ABC, abstractmethod
from typing import Any, Optional

_sov = SovereignLogger("adapters.base")
logger = _sov.logger


class DataProvider(ABC):
    def __init__(self):
        self.available = True
        self.fail_streak = 0
        self.cooldown_until = 0.0

    @property
    @abstractmethod
    def name(self) -> str:
        """Returns the provider name (e.g., 'yfinance', 'morningstar')."""

    @abstractmethod
    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Core fetch logic to be implemented by child classes."""

    async def safe_fetch(self, symbol: str) -> dict[str, Any] | None:
        """Standardized wrapper to prevent provider failures from crashing the loop."""
        if not self.available:
            return None

        try:
            data = await self.fetch_fundamentals(symbol)
            if data and "error" not in data:
                self.fail_streak = 0
                return data
        except Exception as e:
            self.fail_streak += 1
            logger.error(f"Provider {self.name} failed for {symbol}: {str(e)}")
            # If streak is high, temporarily disable or cooldown might be handled by Orchestrator
        return None
