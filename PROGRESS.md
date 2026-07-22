## Done
- **AUDIT LEDGER NOTE (2026-07-22):** (1) Identified dangerous schema drift between Alembic `db/models.py` and live SQLite schema. `db/repository.py::_ensure_column()` has been silently adding active columns (e.g., `revenue_cagr_3y`, `piotroski_score`, `promoter_holding`) at runtime that do not exist in the SQLAlchemy models. Future Alembic autogenerates will destructively attempt to `DROP` these columns. Action required: Either backport all runtime columns to `models.py` to sync Alembic, or officially deprecate Alembic autogenerate and treat `_ensure_column()` as the sole source of schema truth. (2) `jugaad_data` and the `api_keys` test failure represent "works on my machine" bugs where tests run locally because legacy data exists, but fail on fresh clones. Fixed `jugaad_data` by adding to `requirements.txt`.
- Standardized scoring engine boundary key normalization via `normalize_data_keys`.
- Added unit and integration tests for key normalization in [test_normalize_data_keys.py](file:///d:/Tradeidesa/Multibagger-claude/Newmultibagger-main/tests/test_normalize_data_keys.py).
- Fixed `SovereignLogger`'s `critical` method and formatting argument signature compatibility.
- Fixed `asyncpg` create_pool mock in repository tests.
- Fixed `rejected_trades.csv` path verification in blackbox tests.
- Ignored third-party `shap` deprecation warnings in `pytest.ini`.
- Updated Graphify knowledge graph (`graphify-out/`).
- Started FastAPI backend server on port 9005.
- Started React/Vite frontend development server on port 3000.
- Resolved a compatibility issue with `vectorbt` by downgrading `plotly` to version `5.24.1` (below `6.0.0`) in the virtual environment.
- Ran the entire test suite (`pytest -m "not live"`): all 226 tests passed successfully.
- Resolved `/api/stocks` timeout issue by optimizing DuckDB connection initialization in `db/db_core.py` (avoiding redundant network-checking `INSTALL sqlite` calls and doing direct `LOAD sqlite` instead).
  - First-time backend load time for `/api/stocks` reduced from ~34 seconds to under 3 seconds.
- Resolved path resolution bugs in `db_utils.py`, `connections.py`, and `correlation.py` where nested modules was causing database calls to target an empty sqlite file in `modules/runtime/stocks.db` instead of the correct database in `runtime/stocks.db`.
  - The System Data Intelligence pane now successfully loads and displays snapshot age (10D), data quality (100%), and universe breakdown counts (1402 expired).
- Re-added sync `fetch_fundamentals` to `DataManager` in `data_service.py` to fix price/fundamentals analysis endpoint regressions.
- Restored `StockDataPayload` schema policy to ignore extra fields, fixing validation test regressions.
- Successfully executed simulated universe recan and institutional analysis pipeline (Backtest Picks, Alpha Attribution, Liquidity Stress Test, Walk-Forward Validation).
- Passed the Antigravity Master Checklist (`checklist.py`) with 100% green status.
- Implemented multi-worker WebSocket safety using a Redis Pub/Sub backend on the `live:prices` channel (fanning out price ticks to local workers).
- Added query parameter-based authentication (`?token=...` or `?api_key=...`) to WebSocket endpoints.
- Replaced direct `sqlite3.connect` calls in the backtest engine with the pooled `get_db_connection` context manager from `db.db_core` supporting named parameters.
- Fixed metrics allowlist IP-spoofing vulnerability by dropping client-controlled `X-Forwarded-For` header trust and relying only on direct TCP peers or configured proxy IPs.
- Modified holdout evaluations to support custom annualisation periods via `periods_per_year` parameter.
- Replaced non-functional reproducibility check with a rigorous test ensuring statelessness and input immutability in feature sanitisation.
- Adjusted momentum feature leakage checks to flag `NEEDS_REVIEW` only when Spearman correlation `|r| > 0.15`, reducing noise.
- Documented `upstash-redis` as an optional dependency in `requirements.txt`.
- Added warning logs for skipped backtest periods and expanded columns to include `portfolio_value` in the QARP backtest report.
- Removed tracked `graphify-out/` files from Git index.

## In progress

## Next

## Notes
- Ports:
  - Frontend: `http://localhost:3000`
  - Backend API: `http://localhost:9005`
- Authentication Header: `X-API-Key: DEV_KEY_123`

- Corrected 46 previous INFO-level logging errors back to WARNING/ERROR levels across modules to fix swallowed exceptions.
- Refactored SovereignLogger initialization across the codebase (38 files) to correctly use the wrapper and preserve structured JSON fields.
- Secured /ws/signals WebSocket endpoint with API Key validation.
- Fixed _json_safe_clean import paths in score_report.py and dependencies.py.
- Made worker/task_bus.py dispatch() uniformly async to prevent silent caller traps in development mode.
- Added test coverage for worker/task_bus.py in 	ests/test_task_bus.py.

