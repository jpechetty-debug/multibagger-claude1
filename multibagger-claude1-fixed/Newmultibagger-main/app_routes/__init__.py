"""FastAPI routers for the primary application entrypoint."""

from .public import router as public_router

__all__ = ["public_router"]
