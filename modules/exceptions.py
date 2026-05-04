class TradingEngineError(Exception):
    """Base exception class for Sovereign AI Trading Engine."""


class FetchError(TradingEngineError):
    """Raised when there is an error fetching data from external APIs."""


class DataQualityError(TradingEngineError):
    """Raised when data retrieved fails quality validation checks."""


class ScoringError(TradingEngineError):
    """Raised when applying scoring logic fails."""


class DatabaseConcurrencyError(TradingEngineError):
    """Raised when a database concurrent write lock issue occurs."""


class RateLimitError(FetchError):
    """Raised when hitting an API rate limit."""
