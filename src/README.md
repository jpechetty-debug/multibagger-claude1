# Deprecated `src/` Tree

This directory is no longer the active application architecture.

Canonical runtime paths:
- FastAPI app: `main.py`
- CLI: `sovereign_cli.py`
- Core scan orchestration: `screener.py`
- Shared services: `modules/` and `db/`

What remains here:
- `src/main.py` as a backward-compatibility shim for legacy imports
- lightweight deprecation placeholders so stale imports fail softly

Do not add new features under `src/`.
