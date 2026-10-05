## Done
Older history: see `PROGRESS_ARCHIVE.md` (read it only when you need past context).
- 2026-10-06: Research tab API calls fixed (commit `1fa13a4`). ValidationDashboard sent `dev_key_123` (got 403), and ResearchDashboard called a non-existent `/api/v1/research/trust-score` (got 404). Both now go through `lib/api.ts`, and Vite proxies `/research`. Verified with Playwright.
- 2026-10-06: Token hygiene. Removed the one-off root scripts (`fix_tasks.py`, `inject_validation.py`, `audit_runner.py`) and `dupont-roe-decomposition.patch`, all already applied to the code. Added `multibagger-claude1-fixed/` to `.gitignore`. Moved the old Done entries to `PROGRESS_ARCHIVE.md`.

## In progress

## Next
(Cheapest first.)
1. Label the Graphify communities: all 600 are named "Community N". Run `/graphify --update` (needs an LLM). The graph itself is current as of `2d44090`.
2. Small cleanups: collapse the `_sanitize_features` wrapper in `modules/scoring/ml_score.py` into `feature_factory.sanitize_features`, and keep a single logger in `modules/pit_auditor.py` (it has both `_log` and `logger`).
3. The backend `/research/trust-score` response has no `grade` field, so the UI shows an empty "Grade:".
4. Move `ticker_list.py` (1572 lines of data) to CSV/JSON.
5. Split `scripts/internal/screener.py` (2341 lines). It holds `get_stock_data()`, the top god node (58 edges).
6. [OPEN since 2026-07-22] Alembic schema drift: `db/repository.py::_ensure_column()` adds columns at runtime (e.g. `revenue_cagr_3y`, `piotroski_score`) that are missing from `db/models.py`, so an Alembic autogenerate would DROP them. Either backport the columns to the models or retire autogenerate.

## Notes
- Ports: frontend `http://localhost:3000`, backend `http://localhost:9005`. Auth header: `X-API-Key: DEV_KEY_123` (case-sensitive; the wrong case gets 403).
- Start the backend: `cd Newmultibagger-main && .venv/Scripts/python.exe -m uvicorn main:app --port 9005`. Redis connection errors at startup are harmless locally.
- Vite proxies only `/api`, `/swarm`, `/research`, `/ws`. A backend route outside these 404s in dev.
- Frontend code should call the backend through `web-ui/src/lib/api.ts`, never with raw `fetch` and a hardcoded key.
- `vectorbt` needs `plotly<6`. DuckDB uses `LOAD sqlite` (not `INSTALL`) to avoid a ~30 s network check.
- The runtime DB is `Newmultibagger-main/runtime/stocks.db`. Resolve paths from the project root, never relative to `modules/`.
- To save tokens, ask `codegraph_explore` (indexed in `Newmultibagger-main/.codegraph`) before grep/read. Plain grep over the tree is slow because of `.venv` and `.pytest_tmp`.
