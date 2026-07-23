from abc import ABC, abstractmethod
from typing import Any

from core.observability.logger import get_logger

logger = get_logger("adapters.base")


def resolve_key(
    info: dict,
    candidates: tuple[str, ...],
    source: str,
    field: str,
) -> Any:
    """Resolve a canonical field from an info dict using an ordered candidate list.

    Selects the first candidate key that has a non-None value. When more than
    one candidate key is present with a non-None value, emits a structured
    warning so the ambiguity is visible in logs and can be monitored.

    Args:
        info:       Raw dict returned by a data provider.
        candidates: Ordered tuple of key names to try, highest priority first.
        source:     Provider name for the log line ("pnsea", "yfinance", etc.).
        field:      Canonical field name being resolved ("revenue_growth", etc.).

    Returns:
        The value of the first matching candidate key, or None if none found.

    Example:
        >>> resolve_key(
        ...     {"revenueGrowth": 0.15, "salesGrowth": 0.22},
        ...     ("revenueGrowth", "salesGrowth"),
        ...     source="yfinance",
        ...     field="revenue_growth",
        ... )
        0.15   # revenueGrowth wins (first in candidates); conflict is logged
    """
    if not isinstance(info, dict):
        return None

    hits = [
        (k, info[k])
        for k in candidates
        if k in info and info[k] is not None
    ]

    if not hits:
        return None

    if len(hits) > 1:
        logger.warning(
            f"key_conflict | field={field} source={source} found={[k for k, _ in hits]} using={hits[0][0]} candidates={list(candidates)}"
        )

    return hits[0][1]


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
