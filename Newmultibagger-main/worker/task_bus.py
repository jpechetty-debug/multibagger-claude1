"""
Unified task dispatcher — asyncio in dev, Celery in prod.

Usage:
    from worker.task_bus import dispatch

    # In async context:
    await dispatch(scan_single_stock, "RELIANCE", regime="BULLISH")

    # In sync context (Celery prod):
    dispatch(scan_single_stock, "RELIANCE", regime="BULLISH")

Environment:
    CELERY_BROKER_URL  — set to a rediss:// URL to activate Celery mode.
    When unset, tasks run in-process via asyncio.Queue (dev mode).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import os
from typing import Any

from core.observability.logger import get_logger

logger = get_logger("sovereign.task_bus")

_MODE: str = "celery" if os.getenv("CELERY_BROKER_URL") else "asyncio"


# ---------------------------------------------------------------------------
# Asyncio dev-mode dispatcher
# ---------------------------------------------------------------------------

_queue: asyncio.Queue[tuple[Callable, tuple, dict]] | None = None


def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def _dispatch_async(fn: Callable, *args: Any, **kwargs: Any) -> str:
    """Enqueue a callable for the dev worker loop."""
    q = _get_queue()
    await q.put((fn, args, kwargs))
    task_id = f"async-{id(fn)}-{len(args)}"
    logger.info("task.enqueued", mode="asyncio", task=fn.__name__, task_id=task_id)
    return task_id


async def run_dev_worker(*, max_tasks: int = 0) -> None:
    """
    Consume tasks from the asyncio queue (dev mode).

    Args:
        max_tasks: stop after N tasks (0 = run forever).
    """
    q = _get_queue()
    processed = 0
    logger.info("dev_worker.started")
    while True:
        fn, args, kwargs = await q.get()
        try:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                result = await result
            logger.info("task.completed", task=fn.__name__, result_type=type(result).__name__)
        except Exception as exc:
            logger.error("task.failed", task=fn.__name__, error=str(exc))
        finally:
            q.task_done()
        processed += 1
        if max_tasks and processed >= max_tasks:
            break


# ---------------------------------------------------------------------------
# Celery prod-mode dispatcher
# ---------------------------------------------------------------------------

def _dispatch_celery(fn: Callable, *args: Any, **kwargs: Any) -> str:
    """Send task via Celery. Expects fn to be a registered Celery task."""
    from worker.celery_app import app  # noqa: F811 — deferred import

    if not hasattr(fn, "name"):
        raise ValueError(
            f"dispatch(): '{fn.__name__}' is not a registered Celery task. "
            f"Decorate it with @app.task before dispatching."
        )

    task_name = getattr(fn, "name", fn.__name__)
    result = app.send_task(task_name, args=args, kwargs=kwargs)
    logger.info("task.enqueued", mode="celery", task=task_name, task_id=result.id)
    return result.id  # type: ignore


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def dispatch(fn: Callable, *args: Any, **kwargs: Any) -> str:
    """
    Dispatch a task using the active mode.

    Returns the task ID. Must be awaited in both dev and prod modes.
    """
    if _MODE == "celery":
        return _dispatch_celery(fn, *args, **kwargs)
    return await _dispatch_async(fn, *args, **kwargs)


def get_mode() -> str:
    """Return current dispatch mode: 'celery' or 'asyncio'."""
    return _MODE
