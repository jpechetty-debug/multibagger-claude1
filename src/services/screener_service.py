"""
Deprecated service module.

The active screener orchestration now lives in repo-root `screener.py`,
`main.py`, and `modules/services.py`. This file is intentionally reduced to a
deprecation marker so the repository no longer presents two competing service
architectures.
"""

from __future__ import annotations

import warnings


warnings.warn(
    "src.services.screener_service is deprecated. Use screener.py or modules/services.py.",
    DeprecationWarning,
    stacklevel=2,
)

__all__: list[str] = []
