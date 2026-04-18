   # Sovereign Research Terminal v3.0

Sovereign is an institutional-grade quantitative screening and research platform for Indian equities. It integrates the **Nexus Alpha (v11.0)** scoring engine, a **Technical Brutalist** React/Vite dashboard, a normalized regime/risk API, and a hardened **QARP (v4.4)** research stack with trend filters, survivorship-aware backtesting, and portfolio concentration controls.

This README is the operational entrypoint for running the terminal locally. For a deeper layout overview, see [ARCHITECTURE.md](./ARCHITECTURE.md).

## What Is In The Repo

- FastAPI API in [main.py](./main.py)
- Extracted route modules in [app_routes](./app_routes)
- **Nexus Alpha (v11.0)** core scoring and data logic in [modules](./modules)
- Repository and PIT persistence code in [db](./db)
- Standalone background jobs in [worker](./worker)
- **Technical Brutalist** React frontend in [web-ui](./web-ui)
- Regression and contract tests in [tests](./tests)

## Core Intelligence & Hardening (v4.4)

- **Nexus Alpha Scoring**: Sigmoid-normalized multi-factor scoring with spline caps, sector-relative adjustments, and deterministic tie-breaking.
- **Regime Layer**: `/api/regime_status` is backed by the active `MarketDataProvider` contract and returns normalized regime payloads for both the frontend and terminal clients.
- **Allocator Ranking**: GARP proposals now use a Nexus-led composite rank rather than relying on conviction score alone.
- **Backtest Hardening**: QARP backtests include regime-aware exposure, 1-day execution lag, and survivorship-aware universe filtering.
- **Data Pipeline Resilience**: Lazy provider initialization prevents import-time network failures and makes offline testing/CI more stable.

## Canonical Entry Points

- Backend API: `uvicorn main:app --reload --port 9005`
- Runtime worker: `python -m worker.runtime`
- CLI: `python sovereign_cli.py ...`
- Frontend dev server: `cd web-ui && npm run dev`

The repo-root [main.py](./main.py) is the only active web application entrypoint. The `src/` tree is deprecated compatibility scaffolding and should not be used for new work.

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- npm

### Backend Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Notes:
- Local development can run against SQLite without extra database setup.
- See [.env.example](./.env.example) for database, Redis, and risk-governor settings.

### Start The Backend

```powershell
uvicorn main:app --reload --port 9005
```

The API will be available on `http://localhost:9005`.

### Start The Runtime Worker

```powershell
python -m worker.runtime
```

Use the worker when you want background price updates and scheduled maintenance outside the web app process.

Optional:

```powershell
python -m worker.runtime --skip-audit
```

### Start The Frontend

```powershell
cd web-ui
npm install
npm run dev
```

The Vite dev server proxies `/api` and `/ws` requests to `http://localhost:9005`.

## Common CLI Commands

```powershell
python sovereign_cli.py scan quick
python sovereign_cli.py scan swarm --tickers INFY.NS,TCS.NS --deep
python sovereign_cli.py sys health
python sovereign_cli.py sys regime
python sovereign_cli.py research rs-sector  # Ingest Sector RS signals
python sovereign_cli.py paper-trade --universe 50
```

CLI groups currently available:
- `db`
- `scan`
- `ml`
- `research`
- `backtest`
- `sys`
- `paper-trade`

## Frontend/API Contract Notes

The dashboard now relies on a normalized contract layer instead of consuming backend payloads directly:

- Shared frontend-facing types live in [web-ui/src/lib/contracts.ts](./web-ui/src/lib/contracts.ts)
- Backend payload normalization lives in [web-ui/src/lib/api.ts](./web-ui/src/lib/api.ts)
- Dashboard loading, error, refresh, and empty states are handled in [web-ui/src/App.tsx](./web-ui/src/App.tsx) and [web-ui/src/components/signals/SignalGrid.tsx](./web-ui/src/components/signals/SignalGrid.tsx)

The main frontend contract-sensitive endpoints are:
- `/api/stocks`
- `/api/regime_status`
- `/api/health`
- `/api/reports/{symbol}`

Regime API notes:
- `/api/regime_status` returns normalized regime labels such as `BULL`, `BEAR`, `SIDEWAYS`, and `BLACK`
- `/api/regime_status` includes `vix`, `vix_threshold`, `momentum_accel`, `votes`, `is_forced`, `details`, `timestamp`, and optional `stale` / `error`
- `/api/admin/force_regime?regime=BULL|BEAR|SIDEWAYS|AUTO` is the supported manual override contract

## Research / Backtest Notes

- The primary ranking engine lives in [modules/scoring.py](./modules/scoring.py)
- The GARP allocator consumes DB output but now uses a Nexus-led composite rank in [brain/garp_strategy.py](./brain/garp_strategy.py)
- The QARP backtest runner in [backtest_qarp.py](./backtest_qarp.py) applies survivorship filtering via [backtest/survivorship_adjusted_loader.py](./backtest/survivorship_adjusted_loader.py)
- The lightweight vectorized batch engine in [backtest/engine.py](./backtest/engine.py) is still useful for screening-scale momentum validation, but it is not the full institutional QARP simulator

## Testing

Backend:

```powershell
python -m pytest -q -m "not live"
```

Frontend:

```powershell
cd web-ui
npm test
npm run build
```

The frontend test harness is powered by Vitest and Testing Library. The most important current UI contract tests live in:
- [web-ui/src/lib/api.test.ts](./web-ui/src/lib/api.test.ts)
- [web-ui/src/App.test.tsx](./web-ui/src/App.test.tsx)

`pytest.ini` is the single source of truth for pytest behavior in this repo.

Useful backend regression slices:
- `tests/test_regime_api.py`
- `tests/test_api_v96.py`
- `tests/test_garp_strategy.py`
- `tests/test_backtest_engine.py`
- `tests/test_survivorship_loader.py`
- `tests/test_data_service_lazy.py`

## Repo Layout

- [main.py](./main.py): active FastAPI app
- [app_routes](./app_routes): extracted API routers and response contracts
- [modules](./modules): **Nexus Alpha** scoring, data ingestion, and domain services
- [db](./db): repository layer and PIT snapshot logic
- [worker](./worker): background runtime jobs
- [web-ui](./web-ui): **Technical Brutalist** UI
- [tests](./tests): regression and contract coverage
- [src](./src): [DEPRECATED] compatibility path

## Development Notes

- Prefer adding new backend behavior to the active root app and extracted router/modules, not `src/`.
- New runtime artifacts should live in ignored output locations such as `runtime/`, `logs/`, or `reports_cache/`, not as committed source files.
- For architectural context and runtime policy, see [ARCHITECTURE.md](./ARCHITECTURE.md).
