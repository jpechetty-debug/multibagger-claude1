# Architecture

## Canonical Entry Points

- FastAPI app: `uvicorn main:app --reload`
- Runtime worker: `python -m worker.runtime`
- CLI: `python sovereign_cli.py ...` (Centralized operational wrapper)
- Frontend: `web-ui/`

The repo-root `main.py` is the only active web application entry point.

## Active Backend Layout

- `main.py`: FastAPI routes, request orchestration, web-only lifecycle hooks
- `modules/`: domain logic, scoring, data ingestion, research signals
- `modules/strategies/`: Quantitative strategies and allocation logic
- `runtime/`: Database storage, PID files, and local state (IGNORED)
- `worker/`: async/background worker plumbing and standalone runtime jobs
- `scripts/internal/`: Maintenance and operational scripts (Invoked via CLI)
- `tests/`: Regression and contract tests

## Refactored Paths

The legacy `src/` and `brain/` trees have been eliminated. All strategic logic is now centralized in `modules/` or `modules/strategies/`.

## Runtime Artifact Policy

Generated runtime artifacts belong in ignored locations, not in the source tree:

- databases: `runtime/`
- logs: `logs/`
- generated reports/cache: `reports_cache/`, `runtime/`
- scratch/debug outputs: NEVER COMMIT.

## Testing Policy

`pytest.ini` is the single source of truth for pytest behavior.

Current default goal:
- fast local test execution
- explicit markers for slow/live/integration cases
- no implicit doctest collection from text artifacts

Coverage and stricter gates should be increased as the critical modules are brought under stronger test control.
