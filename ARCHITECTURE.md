# Architecture

## Canonical Entry Points

- FastAPI app: `uvicorn main:app --reload`
- Runtime worker: `python -m worker.runtime`
- CLI: `python sovereign_cli.py ...`
- Scan orchestration: `screener.py`
- Frontend: `web-ui/`

The repo-root [`main.py`](D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/main.py) is the only active web application entry point.

## Active Backend Layout

- `main.py`: FastAPI routes, request orchestration, web-only lifecycle hooks
- `modules/`: domain logic, scoring, data ingestion, research signals
- `db/`: schema, repository layer, PIT snapshot storage
- `worker/`: async/background worker plumbing and standalone runtime jobs
- `scripts/internal/`: maintenance and operational scripts
- `tests/`: regression and contract tests

## Deprecated Paths

- `src/main.py`: compatibility shim only
- `src/api/routes.py`: deprecated placeholder
- `src/services/screener_service.py`: deprecated placeholder

New code should not depend on the `src/` tree.

## Runtime Artifact Policy

Generated runtime artifacts belong in ignored locations, not in the source tree:

- databases: `runtime/` or local machine paths
- logs: `logs/`
- generated reports/cache: `reports_cache/`, `runtime/`, or ignored output folders
- scratch/debug outputs: never commit

If a file is needed as a fixture, store a minimal deterministic test fixture under `tests/fixtures/` instead of reusing live runtime data.

## Testing Policy

`pytest.ini` is the single source of truth for pytest behavior.

Current default goal:
- fast local test execution
- explicit markers for slow/live/integration cases
- no implicit doctest collection from text artifacts

Coverage and stricter gates should be increased as the critical modules are brought under stronger test control.
