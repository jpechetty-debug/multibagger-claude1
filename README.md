# Sovereign Research Terminal v9.5

## // Institutional-Grade Multibagger Engine //

Sovereign is a high-conviction screening and research platform designed for structural alpha in Indian equities. It integrates the **Nexus Alpha (v11.0)** scoring system, a **Technical Brutalist** analytical dashboard, the **Multibagger Compounding Lens** (v4.1), and a full-stack **Data Quality & Scoring Intelligence** layer for institutional-grade fundamental auditing.

> [!NOTE]
> **Sovereign is not a black box.** Every score is explainable via the "Why This Score?" panel, every metric is auditable through the Integrated Explainer system, and data freshness is surfaced on every screen — stale data is never hidden.

---

## 🧠 Core Intelligence: Nexus Alpha v11.0

The heart of the terminal is the Nexus Alpha engine, which replaces binary screening cliffs with **Sigmoid-Normalized** multi-factor scoring.

### The 9-Factor Scoring Protocol

Every stock is audited across nine distinct vectors, dynamically weighted by **Market Regime**:

| Factor | Description |
|--------|-------------|
| **Growth** | 5Y Sales and EPS Expansion |
| **Quality** | Multibagger ROE/ROCE splines and Asset-Light CFO/PAT ratios |
| **Value** | Sigmoid-normalized PE/PEG gaps with sector-relative adjustments |
| **Risk** | Institutional **F-Score** floor and Debt/Equity constraints |
| **Momentum** | Composite Relative Strength (RS) + 52-Week High Proximity |
| **Sentiment** | Integrated NLP news sentiment with local LLM fallbacks |
| **Smart Money** | Promoter buying patterns and Institutional anchor analysis |
| **Estimates** | Forward earnings momentum and upgrade/downgrade velocity |

### Institutional Quality Gate

A strict **12-point checklist** enforces a quality floor for long-term compounding candidates. Stocks failing the gate are capped at a maximum "Neutral" score regardless of sheer growth numbers.

### Score Explainability

Every stock score can be decomposed into:
- **Top 3 Positive Drivers** — what's pushing the score up
- **Top 3 Penalties** — what's holding it back
- **Active Score Ceilings** — which spline caps are binding
- **Checklist Grade (A–D)** — pass/fail across 8 institutional criteria
- **Score Delta** — change from previous scan with direction and reason

---

## 📊 Data Freshness & Quality Engine

> [!IMPORTANT]
> **Stale data is never hidden.** The terminal enforces hard freshness rules across the entire pipeline.

### Freshness Status

| Status | Age | Color | Effect |
|--------|-----|-------|--------|
| **FRESH** | ≤ 3 days | 🟢 Green | Full signal confidence |
| **STALE** | 4–7 days | 🟡 Amber | Warning badge, elevated caution |
| **EXPIRED** | > 7 days | 🔴 Red | **BUY signals blocked** — downgraded to WATCH |

### Provider Health Monitoring

Real-time success rate tracking for each data provider:
- **yfinance** — primary fundamental + price data
- **pnsea** — alternate fundamental source
- **nsepython** — NSE-native corporate actions and shareholding

### Universe Quality Alerts

Automated monitoring triggers alerts when >20% of the tracked universe has stale or incomplete fundamentals, surfacing data degradation before it affects research decisions.

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/data-freshness` | Badge data: status, age, quality score, refresh status |
| `GET /api/provider-health` | Per-provider success rates and call counts |
| `GET /api/universe-quality` | Staleness metrics and alert status |

---

## 🔬 Scoring Calibration & Diagnostics

The terminal includes a built-in scoring intelligence layer to detect and diagnose calibration issues:

- **Decile Distribution Histogram** — visualize score spread across 0–100
- **Graveyard Detection** — flags clustering at 59–61 (ceiling convergence)
- **Sector Score Ranges** — per-sector min/max/median with visual range bars
- **Calibration Health** — GOOD / NEEDS_ATTENTION / POOR with specific fix recommendations
- **Top 5% Rarity** — tracks how selective the scoring engine is

### API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/score-distribution` | Deciles, stats, sector breakdown |
| `GET /api/score-explain/{symbol}` | Full per-stock explanation |
| `GET /api/calibration-report` | Overall calibration health |

---

## 🔍 Multibagger Compounding Lens (v4.1)

Designed to identify "structural survivors," this lens applies deep-dive fundamental auditing:

- **Quarterly Results Timeline**: Visual drift analysis of P&L and Balance Sheet integrity over time.
- **10-Year CAGR Engine**: Rolling returns and compounding consistency scores.
- **Survivorship-Aware Backtesting**: QARP results that account for delistings and universe changes.
- **Earnings Inflection Detection**: Automated alerts for margin breakouts and volume-led growth shifts.

---

## 🛡️ Research UX

### Red Flag Detection

Automated risk alerts with severity levels (CRITICAL / WARNING):

| Flag | Trigger |
|------|---------|
| High Promoter Pledge | > 10% pledged |
| Dangerous Debt | D/E > 1.0 |
| Low Promoter Holding | < 40% |
| Weak Cash Quality | CFO/PAT < 0.7 |
| Stretched Valuation | PE > 50 |

### Personal Watchlist

Browser-persistent watchlist with `localStorage`:
- Add/remove stocks from any detail page
- Orphaned symbol detection (saved but no longer in universe)
- Watchlist count badge in the header

### Score Report Dashboard

Accessible at `/score-report` — a dedicated page for scoring engine health:
- Decile histogram with graveyard highlighting
- Sector score range visualization
- Calibration health panel with issue severity
- Provider health integration

---

## 🏗️ System Architecture

```mermaid
graph TD
    UI[Technical Brutalist Dashboard] --> API[FastAPI Orchestrator]
    API --> Scoring[Nexus Alpha Engine]
    API --> Freshness[Data Freshness Engine]
    API --> Diagnostics[Score Diagnostics]
    API --> DB[(SQLite — WAL Mode)]
    Scoring --> Data[yfinance / pnsea / nsepython]
    Freshness --> Cache[(data_cache.db)]
    Worker[Runtime Worker] --> Scoring
    Worker --> Maintenance[Audit & Cleanup]
    CLI[Sovereign CLI] --> API
    Health[/api/health/deep] --> DB
    Health --> Cache
    Health --> Freshness
```

### Stack Components

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy, Pydantic v2 |
| **Frontend** | React 18, Vite, TailwindCSS, Framer Motion, Recharts, Lucide |
| **Database** | SQLite (WAL mode) with PIT snapshots in `fundamentals_pit` |
| **Caching** | File-backed SQLite cache (`data_cache.db`) |
| **Observability** | Prometheus + structured JSON logging |
| **CI/CD** | GitHub Actions (lint, type-check, pytest, frontend build, syntax gate) |

---

## 🚀 Quickstart

### 1. Backend API

```powershell
pip install -r requirements.txt
uvicorn main:app --reload --port 9005
```

### 2. Frontend Dashboard

```powershell
cd web-ui
npm install
npm run dev
```

Accessible at `http://localhost:5173`. Proxies API requests to port 9005.

### 3. Runtime Worker

```powershell
python -m worker.runtime
```

Background price updates, liquidity audits, and scheduled PIT maintenance.

### 4. Sovereign CLI

```powershell
python sovereign_cli.py scan quick          # Immediate market pulse
python sovereign_cli.py sys health          # Integrity check
python sovereign_cli.py research update-rs  # Refresh momentum signals
```

### 5. Database Backup

```powershell
python scripts/backup_restore.py backup           # Create timestamped backup
python scripts/backup_restore.py list              # List available backups
python scripts/backup_restore.py restore <path>    # Restore from backup
python scripts/backup_restore.py prune --keep 5    # Retain only 5 most recent
```

---

## 📈 Operational Universe

The terminal tracks **1,500+ NSE Equities** with automated expansion and curation:

- **High-Conviction Sectors**: Special coverage for Defense, EMS, Renewables, and Niche Tech.
- **Universe Expansion**: Managed via `add_tickers.py` and `curator.py`.
- **Data Hardening**: Lazy-loaded providers with cache fallbacks ensure 99.9% uptime.

---

## 🔒 Production Hardening

### Deep Health Check

`GET /api/health/deep` validates all subsystems in a single call:

| Check | What It Validates |
|-------|-------------------|
| **Database** | SQLite connectivity + stock count |
| **Cache** | `data_cache.db` existence and integrity |
| **Data Freshness** | Latest snapshot age + quality score |
| **Providers** | yfinance/pnsea/nsepython success rates |
| **Background Worker** | Price updater task status |

Returns `"healthy"` or `"degraded"` with per-check details.

### Structured Error Responses

All API errors use a consistent `SovereignError` shape:

```json
{
  "error_code": "STALE_DATA",
  "message": "Data for RELIANCE.NS is 12 days old — exceeds freshness threshold",
  "details": { "symbol": "RELIANCE.NS", "age_days": 12 },
  "timestamp": "2026-04-27T12:00:00"
}
```

### Environment-Gated Security

| Mode | `SOVEREIGN_ENV` | API Key Enforcement |
|------|-----------------|---------------------|
| **Production** | `production` | `X-API-Key` header required on every request |
| **Local** | `local` (default) | Permissive — no key required |

---

## 🧪 Testing & CI

### Backend (Pytest)

```powershell
python -m pytest tests/ -q
```

### Frontend (Vitest)

```powershell
cd web-ui
npm test
```

### CI Pipeline (GitHub Actions)

| Job | What It Runs |
|-----|-------------|
| **Lint** | `ruff check` + `ruff format --check` |
| **Type Check** | `mypy --config-file pyproject.toml` |
| **Tests** | `pytest` with coverage reporting |
| **Frontend** | `npm ci` → `npm run build` → `npm test` |
| **Syntax Gate** | BOM detection + AST parse validation |

---

## 🗂️ Key File Map

```
├── main.py                         # FastAPI entry point
├── config.py                       # Scoring weights, thresholds, universe config
├── sovereign_cli.py                # CLI entry point
├── modules/
│   ├── scoring.py                  # Nexus Alpha scoring engine
│   ├── hybrid_scoring.py           # XGBoost meta-model layer
│   ├── data_freshness.py           # Freshness status, provider health, BUY gating
│   ├── score_diagnostics.py        # Distribution analysis, explanations, calibration
│   ├── errors.py                   # Structured error responses
│   ├── data_service.py             # Data fetching and caching
│   ├── dependencies.py             # Runtime config and security
│   └── services.py                 # Service layer abstractions
├── app_routes/
│   ├── stocks.py                   # Stock CRUD and thesis endpoints
│   ├── freshness.py                # Data freshness API
│   ├── score_report.py             # Score distribution API
│   ├── public.py                   # Health checks (shallow + deep)
│   ├── regime.py                   # Market regime status
│   └── system.py                   # System admin endpoints
├── web-ui/src/
│   ├── App.tsx                     # Router and layout
│   ├── pages/
│   │   ├── StockDetail.tsx         # Detail view + ScoreExplainer + RedFlags
│   │   ├── Watchlist.tsx           # Personal watchlist page
│   │   └── ScoreReport.tsx         # Scoring intelligence dashboard
│   ├── components/
│   │   ├── metrics/DataFreshnessBadge.tsx
│   │   ├── metrics/ProviderHealthPanel.tsx
│   │   ├── signals/ScoreExplainer.tsx
│   │   ├── signals/RedFlagPanel.tsx
│   │   └── signals/SignalGrid.tsx
│   └── lib/
│       ├── api.ts                  # API client + BUY-label stale gating
│       ├── contracts.ts            # TypeScript data contracts
│       └── useWatchlist.ts         # localStorage watchlist hook
├── scripts/
│   └── backup_restore.py          # DB backup, restore, prune
└── .github/workflows/ci.yml       # Full-stack CI pipeline
```

---

## 🛠️ Development Philosophy

- **Technical Brutalism**: Data density, clarity, and performance over decorative fluff.
- **Deterministic Logic**: Scoring lives in pure modules ([modules/scoring.py](./modules/scoring.py)) for backtest parity.
- **Stale Data is Obvious**: Freshness badges, BUY-label blocking, and universe alerts ensure data quality is always visible.
- **Score Transparency**: Every score is decomposable into drivers, penalties, ceilings, and checklist grades.
- **Explicit Ownership**: Repo-root [main.py](./main.py) is the source of truth.

---

*Built for institutions, accessible for individuals. Sovereign Terminal v9.5.*
