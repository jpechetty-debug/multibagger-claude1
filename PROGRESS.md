## Done
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

## In progress

## Next

## Notes
- Ports:
  - Frontend: `http://localhost:3000`
  - Backend API: `http://localhost:9005`
- Authentication Header: `X-API-Key: DEV_KEY_123`
