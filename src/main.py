"""
src/main.py — DEPRECATED ENTRY POINT
-------------------------------------
The canonical application entry point is the root `main.py` (FastAPI app).

This file is kept for backward compatibility only. It will be removed in a
future sprint once all tooling references have been updated.

Start the application with:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Or in production:
    gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
"""
import warnings
import sys

warnings.warn(
    "src/main.py is deprecated. Use the root main.py entry point: "
    "uvicorn main:app --host 0.0.0.0 --port 8000",
    DeprecationWarning,
    stacklevel=1,
)

# Re-export the canonical app so imports like `from src.main import app` still work.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
from main import app  # noqa: F401, E402

if __name__ == "__main__":
    raise SystemExit(
        "Use the canonical entry point: uvicorn main:app --host 0.0.0.0 --port 8000"
    )
