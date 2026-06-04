"""
Unified observability logger for the Sovereign trading engine.

Provides a single entry-point for structured logging across all modules.
Uses the project-standard SovereignLogger internally.

Usage:
    from core.observability.logger import log

    log.info("screener.run", ticker="RELIANCE", score=0.92)
    log.error("task.failed", task="scan_single_stock", error="timeout")
"""

from __future__ import annotations

from core.observability.logger import get_logger

# Project-wide singleton — all modules share one logger tree.
log = get_logger("sovereign")


def get_logger(name: str) -> SovereignLogger:
    """Return a namespaced logger.

    Example:
        logger = get_logger("sovereign.worker.tasks")
    """
    return SovereignLogger(name)
