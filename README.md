# Sovereign AI Trading Engine

Sovereign is a quantitative screening and research platform for Indian equities. It combines a FastAPI backend, a React/Vite dashboard, point-in-time data storage, a scoring engine, CLI workflows for scans and backtests, and a standalone worker for recurring runtime jobs.

This README is the operational entrypoint for running the project locally. For a deeper layout overview, see [ARCHITECTURE.md](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/ARCHITECTURE.md).

## What Is In The Repo

- FastAPI API in [main.py](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/main.py)
- Extracted route modules in [app_routes](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/app_routes)
- Core screening, scoring, and data logic in [modules](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/modules)
- Repository and PIT persistence code in [db](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/db)
- Standalone background jobs in [worker](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/worker)
- React frontend in [web-ui](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui)
- Regression and contract tests in [tests](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/tests)

## Canonical Entry Points

- Backend API: `uvicorn main:app --reload`
- Runtime worker: `python -m worker.runtime`
- CLI: `python sovereign_cli.py ...`
- Frontend dev server: `cd web-ui && npm run dev`

The repo-root [main.py](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/main.py) is the only active web application entrypoint. The `src/` tree is deprecated compatibility scaffolding and should not be used for new work.

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
- See [.env.example](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/.env.example) for database, Redis, and risk-governor settings.

### Start The Backend

```powershell
uvicorn main:app --reload
```

The API will be available on `http://localhost:8000`.

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

The Vite dev server proxies `/api` requests to `http://localhost:8000`.

## Common CLI Commands

```powershell
python sovereign_cli.py scan quick
python sovereign_cli.py scan swarm --tickers INFY.NS,TCS.NS --deep
python sovereign_cli.py sys health
python sovereign_cli.py sys regime
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

- Shared frontend-facing types live in [web-ui/src/lib/contracts.ts](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui/src/lib/contracts.ts)
- Backend payload normalization lives in [web-ui/src/lib/api.ts](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui/src/lib/api.ts)
- Dashboard loading, error, refresh, and empty states are handled in [web-ui/src/App.tsx](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui/src/App.tsx) and [web-ui/src/components/signals/SignalGrid.tsx](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui/src/components/signals/SignalGrid.tsx)

The main frontend contract-sensitive endpoints are:
- `/api/stocks`
- `/api/regime_status`
- `/api/health`
- `/api/reports/{symbol}`

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
- [web-ui/src/lib/api.test.ts](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui/src/lib/api.test.ts)
- [web-ui/src/App.test.tsx](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui/src/App.test.tsx)

`pytest.ini` is the single source of truth for pytest behavior in this repo.

## Repo Layout

- [main.py](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/main.py): active FastAPI app
- [app_routes](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/app_routes): extracted API routers and response contracts
- [modules](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/modules): screening, scoring, data ingestion, and domain services
- [db](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/db): schema and repository layer
- [worker](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/worker): background runtime jobs
- [web-ui](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/web-ui): React/Vite client
- [tests](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/tests): regression and contract coverage
- [src](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/src): deprecated compatibility path

## Development Notes

- Prefer adding new backend behavior to the active root app and extracted router/modules, not `src/`.
- New runtime artifacts should live in ignored output locations such as `runtime/`, `logs/`, or `reports_cache/`, not as committed source files.
- For architectural context and runtime policy, see [ARCHITECTURE.md](/D:/Tradeidesa/Multibagger-claude/Newmultibagger-main/ARCHITECTURE.md).
