# Contributing to Newmultibagger

## Quick start

```bash
git clone <repo>
cd Newmultibagger
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # fill in API keys
uvicorn main:app --reload     # single canonical entry point
```

## Architecture rules (non-negotiable)

| Rule | Why |
|------|-----|
| **One entry point** — `uvicorn main:app` | `src/main.py` is a deprecated shim; `screener.py` is a library |
| **One DB layer** — `db/engine.py` (SQLAlchemy 2.0) for new code | `database.py` is legacy raw-SQL; migrate callers incrementally |
| **Pinned dependencies** — never remove `==` pins from `requirements.txt` | Unpinned = non-deterministic builds |
| **No committed artifacts** — `.gitignore` blocks `*.csv`, `*.zip`, `*.bak*` | Use `reports_cache/` (gitignored) for output files |
| **Wrong-repo files stay out** — `sovereign_cli.py` etc. belong in sovereign-engine | Check the WRONG_REPO banner before touching those files |

## Branch & PR workflow

```
main          ← production-stable; CI must be green
develop       ← integration branch; merge feature branches here first
feature/xxx   ← your work
```

PRs require:
- CI green (lint + type-check + syntax-gate + unit tests)
- At least one reviewer approval
- No new `*.bak` / `*.csv` / `*.zip` files in the diff

## Running tests

```bash
# Unit tests only (fast, no external API calls)
pytest -m "not live and not integration"

# Full suite (requires API keys + running DB)
pytest

# Single module
pytest tests/test_scoring_engine.py -v
```

Mark any test that calls yfinance / Alpha Vantage / NSE with `@pytest.mark.live`.  
Mark any test that needs a populated DB with `@pytest.mark.integration`.  
CI skips both; they run manually or in a nightly job.

## Adding a new module

1. Create `modules/your_module.py` — **UTF-8, no BOM, typed signatures**
2. Add unit tests in `tests/test_your_module.py`
3. If it calls an external API, wrap calls with a `CircuitBreaker` from `modules/retry_utils`
4. If it needs DB access, use `db/engine.py` (not `database.py`)

## Scoring engine changes

`modules/scoring.py` is the highest-value file in the repo. Any change here needs:
- A written rationale comment in the PR description
- A test in `tests/test_scoring_engine.py` that pins the output for at least 3 stocks
- Regime-mode coverage (bull / bear / balanced paths)

## Environment variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `ALPHA_VANTAGE_API_KEY` | No | — | Fundamental data enrichment |
| `DATABASE_URL` | No | `sqlite:///stocks.db` | SQLite (dev) or PostgreSQL (prod) |
| `REDIS_URL` | No | `redis://localhost:6379` | Celery broker |
| `VIX_KILL_SWITCH` | No | `25` | Hard market halt threshold |
| `MAX_SECTOR_EXPOSURE` | No | `0.30` | Risk governor cap |

Copy `.env.example` to `.env`. Never commit `.env`.
