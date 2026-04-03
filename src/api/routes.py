"""
Deprecated router module.

The live FastAPI surface now lives in the repo-root `main.py`.
This file remains only as a compatibility placeholder so stale imports fail
softly instead of pointing to a broken alternate architecture.
"""

from __future__ import annotations

import warnings

from fastapi import APIRouter


warnings.warn(
    "src.api.routes is deprecated. Use the canonical FastAPI app in root main.py.",
    DeprecationWarning,
    stacklevel=2,
)

router = APIRouter()
