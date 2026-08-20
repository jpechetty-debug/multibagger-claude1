"""
Unified task dispatcher — asyncio only.

Usage:
    from worker.task_bus import dispatch

    # In async context:
    await dispatch(scan_single_stock, "RELIANCE", regime="BULLISH")
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from core.observability.logger import get_logger

logger = get_logger("sovereign.task_bus")

_MODE: str = "asyncio"

# ---------------------------------------------------------------------------
# Asyncio dispatcher
# ---------------------------------------------------------------------------

_queue: asyncio.Queue[tuple[Callable, tuple, dict]] | None = None


def _get_queue() -> asyncio.Queue:
    global _queue
    if _queue is None:
        _queue = asyncio.Queue()
    return _queue


async def _dispatch_async(fn: Callable, *args: Any, _task_options: dict | None = None, **kwargs: Any) -> str:
    """Enqueue a callable for the dev worker loop."""
    q = _get_queue()
    await q.put((fn, args, kwargs))
    task_id = f"async-{id(fn)}-{len(args)}"
    logger.info("task.enqueued", mode="asyncio", task=fn.__name__, task_id=task_id)
    return task_id


async def run_dev_worker(*, max_tasks: int = 0) -> None:
    """
    Consume tasks from the asyncio queue.

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
# Public API
# ---------------------------------------------------------------------------

async def dispatch(fn: Callable, *args: Any, _task_options: dict | None = None, **kwargs: Any) -> str:
    """
    Dispatch a task using asyncio.

    Returns the task ID. Must be awaited.
    """
    return await _dispatch_async(fn, *args, _task_options=_task_options, **kwargs)


def get_mode() -> str:
    """Return current dispatch mode: 'asyncio'."""
    return _MODE


def get_bus_status() -> dict:
    """Return bus status showing mode and queue depth."""
    status = {"mode": _MODE, "queue_depth": 0}
    if _queue is not None:
        status["queue_depth"] = _queue.qsize()
    return status
