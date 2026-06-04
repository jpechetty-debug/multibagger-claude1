"""
Unified observability logger for the Sovereign trading engine.

Provides a single entry-point for structured logging across all modules.
Uses the project-standard SovereignLogger internally (JSON file + color console).

Usage:
    from core.observability.logger import log

    log.info("screener.run", ticker="RELIANCE", score=0.92)
    log.error("task.failed", task="scan_single_stock", error="timeout")

Module-scoped logger:
    from core.observability.logger import get_logger
    logger = get_logger("sovereign.worker.tasks")
    logger.info("task.enqueued", task_name="scan_single_stock")
"""

from __future__ import annotations

from modules.structured_logger import SovereignLogger

# Project-wide singleton — all modules share one logger tree.
log = SovereignLogger("sovereign")


def get_logger(name: str) -> SovereignLogger:
    """Return a namespaced logger."""
    return SovereignLogger(name)
