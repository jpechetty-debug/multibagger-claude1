# Changelog

All notable changes to Newmultibagger are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased] — Sprint: Infrastructure Hardening

### Fixed
- **BOM characters removed** from `modules/risk.py`, `modules/peer_analysis.py`,
  `modules/logger.py`, `modules/quarterly_results.py` — these files previously
  caused `SyntaxError` on import on any non-Windows interpreter.
- **`modules/alpha_vantage.py` syntax error** on line 8 fixed — broken
  `from config\nimport ... ALPHA_VANTAGE_API_KEY` reconstructed into a valid
  `from config import ALPHA_VANTAGE_API_KEY as API_KEY`.
- All 170+ Python files now pass `ast.parse` with zero failures (CI syntax gate added).

### Added
- **Pinned `requirements.txt`** — all critical packages now carry `==` version locks
  (`fastapi==0.115.5`, `pandas==2.2.3`, `xgboost==2.1.3`, `sqlalchemy==2.0.36`, etc.).
  Fresh `pip install` is now deterministic.
- **`requirements-dev.txt`** — test, lint, and type-checking tools separated from
  production dependencies.
- **`pyproject.toml`** — single source of truth for pytest, ruff, and mypy config.
  Replaces ad-hoc tool invocations.
- **GitHub Actions CI** (`.github/workflows/ci.yml`) — four jobs:
  - `syntax-check` — BOM detector + `ast.parse` gate on every push
  - `lint` — ruff check + format
  - `type-check` — mypy on `modules/scoring.py`, `modules/retry_utils.py`, `db/`
  - `test` — pytest unit suite (live/integration tests excluded)
- **Circuit breaker** (`CircuitBreaker` class in `modules/retry_utils.py`) —
  thread-safe CLOSED → OPEN → HALF_OPEN state machine for `yfinance`, `alpha_vantage`,
  and `nse` data sources. Module-level singletons: `yfinance_cb`, `alpha_vantage_cb`,
  `nse_cb`.
- **Type annotations on `modules/scoring.py`** — `normalize_metric`, 
  `calculate_sector_medians`, `calculate_institutional_score` now carry full PEP 484
  signatures. Type aliases `_StockData`, `_SectorMedians`, `_Number` defined.
- **`CONTRIBUTING.md`** — architecture rules, branch workflow, test marking
  conventions, and environment variable reference.
- **`.gitignore` hardened** — added `*.zip`, `*.bak`, `*.bak_fix*`, `extracted_*/`,
  `*.csv`, `sovereign-cli.py`, `sovereign_analyst_reports.py`, `sovereign_mcp.py`.
- **`database.py` DATABASE_URL shim** — respects `DATABASE_URL` env var to resolve
  `sqlite:///` paths, and warns loudly if a non-SQLite URL is set (directing callers
  to `db/engine.py`).

### Changed
- **`screener.py` is now a library** — `if __name__ == "__main__"` block replaced
  with a `SystemExit` that redirects users to `uvicorn main:app`.
- **`src/main.py` is now a deprecated shim** — emits `DeprecationWarning` and
  re-exports `app` from root `main.py` for backward compatibility. Will be removed
  in the next sprint.
- **Wrong-repo sovereign files marked** — `sovereign-cli.py`,
  `sovereign_analyst_reports.py`, `sovereign_mcp.py` now carry a `WRONG REPOSITORY`
  banner. Migration to `sovereign-engine` repo tracked in issue #SOVEREIGN-MIGRATION.

### Architecture decisions
- **Canonical entry point: `main.py`** — `uvicorn main:app --host 0.0.0.0 --port 8000`
- **Canonical DB layer: `db/engine.py`** — SQLAlchemy 2.0, supports SQLite (dev) and
  PostgreSQL/TimescaleDB (prod) via `DATABASE_URL`. New code must not import `database.py`.
- `database.py` remains for the 8 existing callers; migrate them incrementally.

---

## [2.x] — Phase 67: Point-in-Time Data Integrity

- PIT auditor (`modules/pit_auditor.py`) prevents forward-looking bias in backtests
- `fundamentals_pit` table with `(symbol, as_of_date)` primary key
- 72-test suite added

## [1.x] — Phase 23–43: Quant Engine

- Sigmoid normalisation replacing binary scoring cliffs
- HMM regime classifier (`modules/regime_hmm.py`)
- HRP portfolio allocation (`modules/allocation_hrp.py`)
- Survivorship-adjusted backtest loader
- LLM thesis validator (`modules/llm_validator.py`)
- Dynamic factor weights (BULL / BEAR / SIDEWAYS / BALANCED modes)
