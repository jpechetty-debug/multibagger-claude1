import asyncio
import inspect
from typing import Any, Awaitable, Callable, Optional, Sequence


DEFAULT_BACKOFF_SECONDS: Sequence[float] = (2.0, 4.0, 8.0)


def is_rate_limited_error(exc: Exception) -> bool:
    message = str(exc).lower()
    patterns = (
        "too many requests",
        "rate limited",
        "rate limit",
        "429",
        "throttl",
    )
    return any(pattern in message for pattern in patterns)


async def run_with_exponential_backoff(
    operation: Callable[[], Any],
    *,
    context: str = "",
    retry_delays: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
    should_retry: Optional[Callable[[Exception], bool]] = None,
) -> Any:
    """
    Execute an operation with deterministic exponential backoff.
    Retry schedule: 2s -> 4s -> 8s (default).
    """
    retry_check = should_retry or is_rate_limited_error
    retries = len(retry_delays)

    for attempt in range(retries + 1):
        try:
            result = operation()
            if inspect.isawaitable(result):
                return await result  # type: ignore[no-any-return]
            return result
        except Exception as exc:
            if attempt >= retries or not retry_check(exc):
                raise

            wait = float(retry_delays[attempt])
            if context:
                print(f"{context} rate-limited. Retrying in {wait:.0f}s.")
            await asyncio.sleep(wait)

    raise RuntimeError("Retry loop exited unexpectedly")


# ── Circuit Breaker ────────────────────────────────────────────────────────────

import time
import threading
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"       # normal — requests pass through
    OPEN = "open"           # tripped — requests fail-fast
    HALF_OPEN = "half_open" # probing — one request let through


class CircuitBreaker:
    """
    Thread-safe circuit breaker for external data-source calls.

    Usage::

        cb = CircuitBreaker(name="yfinance", failure_threshold=5, recovery_timeout=60)

        @cb.call
        def fetch():
            return yf.download(symbol)

    States
    ------
    CLOSED   → requests pass through; consecutive failures increment counter.
    OPEN     → requests are rejected immediately after *failure_threshold* failures.
               Transitions to HALF_OPEN after *recovery_timeout* seconds.
    HALF_OPEN → one probe request is allowed; success resets to CLOSED,
               failure resets the timeout and returns to OPEN.
    """

    def __init__(
        self,
        name: str = "circuit",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._eval_state()

    def call(self, func: Callable) -> Callable:
        """Decorator / wrapper that guards *func* behind this circuit breaker."""
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self._execute(func, *args, **kwargs)

        return wrapper

    def _execute(self, func: Callable, *args, **kwargs):
        with self._lock:
            state = self._eval_state()

            if state == CircuitState.OPEN:
                raise RuntimeError(
                    f"[CircuitBreaker:{self.name}] OPEN — "
                    f"refusing call, recovery in "
                    f"{self.recovery_timeout - (time.monotonic() - self._opened_at):.0f}s"
                )

            if state == CircuitState.HALF_OPEN:
                # Transition optimistically; rollback on failure
                self._state = CircuitState.HALF_OPEN

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    # ── internals ─────────────────────────────────────────────────────────────

    def _eval_state(self) -> CircuitState:
        """Must be called with self._lock held."""
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
        return self._state

    def _on_success(self) -> None:
        with self._lock:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        with self._lock:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()


# ── Module-level singletons — one per external data source ────────────────────
yfinance_cb = CircuitBreaker(name="yfinance", failure_threshold=5, recovery_timeout=60)
nse_cb = CircuitBreaker(name="nse", failure_threshold=5, recovery_timeout=30)
