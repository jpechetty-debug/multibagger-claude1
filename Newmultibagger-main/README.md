# Sovereign Research Terminal v4.3.0
## // Institutional-Grade Quantitative Research & Data Integrity //

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![SQLite + DuckDB](https://img.shields.io/badge/Database-SQLite%20%2B%20DuckDB-orange.svg)]()
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)]()
[![React Vite](https://img.shields.io/badge/Frontend-React%20Vite-61dafb.svg)]()
[![Pydantic v2](https://img.shields.io/badge/Validation-Pydantic%20v2-red.svg)]()
[![Nexus Alpha](https://img.shields.io/badge/Nexus%20Alpha-v12.5-gold.svg)]()

Sovereign v4.3.0 is an advanced equity research platform designed for structural reliability, point-in-time (PIT) auditing, and high-conviction quantitative signaling across 2,000+ Indian equity tickers. It features a **hardened data quality pipeline**, **multi-provider fundamental fallback chain**, **sigmoid-normalized factor scoring**, and **XGBoost-powered alpha signals**.

> [!IMPORTANT]
> **Data Integrity First.** v4.3.0 enforces proactive Data Quality (DQ) gates, Circuit Breakers, return-based risk correlation, and SEBI filing lag rules, ensuring low-quality upstream data or look-ahead bias never corrupts backtests or live trade signals.

---

## 🏗️ The Data Correctness Pipeline (Hardened)

To eliminate silent failures, scale ambiguity, and look-ahead bias, Sovereign implements a **6-Layer Hardening Architecture**:

1. **Ingestion Boundary**: Pydantic v2 models (`modules/models.py`) with `extra="ignore"` and auto-scaling validators that detect and correct fraction-to-percent ambiguity (e.g., ROE 0.15 → 15.0%).
2. **Circuit Breakers**: Thread-safe `CLOSED → OPEN → HALF_OPEN` state machines (`modules/retry_utils.py`) for resilient data ingestion from `yfinance` and `nse`.
3. **Data Quality (DQ) Gates**: Proactive physical-limit validators (`modules/dq_gates.py`) that clamp metrics to realistic ranges (e.g., PE capped at 1000) and generate DQ flags.
4. **Multi-Provider Fundamental Fallback Layer**: Priority fallback chain (`ScreenerInProvider` → `NSEXBRLProvider` → `PNSEAProvider` → `NSEPythonProvider`) for robust fundamental retrieval. `NSEXBRLProvider` parses official audited filing XBRL for precise Debt/Equity, Book Value, ROE%, and TTM growth metrics.
5. **Quarter-Sensitive SEBI PIT Lag Rules**: SEBI mandates quarterly results within 45 days, but grants **60 days for Q4 (March annual audited results)**. `NSEXBRLProvider` and `pit_auditor.py` dynamically apply 60 days lag for March quarter-end filings and 45 days for Q1–Q3, eliminating Q4 look-ahead bias in backtests.
6. **Pure Math & Turnaround Recovery Engines**: Calculation modules (CAGR, ROE, F-Score) are pure functions. `cagr_engine.py` supports turnaround recovery growth computation (`_turnaround_growth`) for candidates recovering from negative base earnings.

---

## 🔍 Core Analytical Modules

### 1. The Compounding Lens
Deep analysis of structural growth and shareholder returns:
- **DuPont ROE Decomposition**: Breaks down ROE into Net Margin, Asset Turnover, and Financial Leverage.
- **CAGR Purity & Turnaround Recovery**: 3Y and 5Y Revenue, PAT, and EPS CAGRs with turnaround recovery metrics for negative base PAT.
- **Earnings Velocity**: Linear regression of net margins across quarters.
- **Friction-Aware Liquidity Gate**: Pre-trade slippage rejection and volume verification (`volume_verified` tracking).

### 2. Nexus Alpha v12.5 Scoring Engine
Dynamically weighted factors based on **Market Regime** (Bull/Bear/Sideways detected via HMM classifier):
- **Growth (15%)**: Sigmoid-normalized Sales and EPS expansion.
- **Quality (15%)**: Average ROE (5Y) + Cashflow validation (CFO/PAT).
- **Risk (10%)**: Institutional-grade F-Score floor + Debt/Equity constraints.
- **ML Meta-Model**: Meta-scoring layer using XGBoost and SHAP for explainable AI alpha.

### 3. Portfolio Risk & Quantitative Backtesting
- **Return-Based Portfolio Risk Correlation**: Pearson correlation matrix computed on **daily percentage returns** (`close_prices.pct_change()`) in `modules/risk/correlation.py` to prevent false cluster alerts caused by non-stationary price level trends.
- **Sector-Relative Filtering**: Evaluates ROE/Growth/PE against sector medians.
- **Sector-Wise RS Ingestion**: Automated ingestion of high-conviction signals from Relative Strength (RS) screens into the database.
- **HRP Portfolio Allocation**: Hierarchical Risk Parity portfolio construction based on signal conviction.
- **Sovereign QARP Institutional Validation**: Backtesting framework with reproducible random universe sampling (`--sample-seed`), ticker deduplication, and minimum portfolio position floors (`--min-positions`).

---

## ⚡ Architecture & Infrastructure

Sovereign leverages a **SQLite + DuckDB + PostgreSQL** approach:
- **Canonical DB Layer**: `db/engine.py` supports local SQLite testing and production PostgreSQL/TimescaleDB via `DATABASE_URL`.
- **Lightning Queries**: Analytical sorting and filtering across 2,000+ records via DuckDB in <5ms.
- **Point-In-Time (PIT) Auditing**: Fundamentals snapshots stored systematically in `pit_store.db` to prevent forward-looking bias.
- **Technical Brutalist UI**: High-performance, Vite-powered React/TypeScript terminal interface in `web-ui/`.
- **FastMCP Agentic AI**: Built-in FastMCP server for LLM integration with persistent Research Memory and Swarm Intelligence.

---

## 🚀 Getting Started

### 1. Installation & Setup
```bash
# Clone and install backend
git clone https://github.com/your-repo/sovereign-terminal.git
cd sovereign-terminal/Newmultibagger-main
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Initialize System via CLI
python sovereign_cli.py sys setup
python sovereign_cli.py db init
```

### 2. Start the Backend API
The FastAPI server is the primary web backend entry point.
```bash
uvicorn main:app --reload --port 9005
```

### 3. Start the Web UI Terminal
```bash
# In a new terminal tab
cd web-ui
npm install
npm run dev
```

### 4. Operational CLI Workflow
The `sovereign_cli.py` is the unified, authoritative entry point for all research tasks:
```bash
# Run a full universe scan (NSE stocks)
python sovereign_cli.py scan quick

# Train the ML Meta-Model
python sovereign_cli.py ml train

# Ingest Relative Strength signals
python sovereign_cli.py rs ingest

# Run strategy backtests
python sovereign_cli.py backtest run
```

---

## 🛠️ Environment Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `SOVEREIGN_API_KEY` | Production API Security | None (Required in Prod) |
| `SOVEREIGN_ENV` | Environment Context | `local` |
| `DATABASE_URL` | SQLAlchemy Connection URL | `sqlite:///multibaggers.db` |
| `REDIS_URL` | Redis cache/Celery broker | `redis://localhost:6379/0` |
| `NSE_COOKIE` | Browser cookie for `NSEXBRLProvider` | None (Optional) |
| `NSE_XBRL_MAX_FILINGS` | Filing depth for XBRL adapter | `8` |
| `NSE_XBRL_PIT_LAG_DAYS` | Standard quarterly filing lag (days) | `45` |

---

## 🧪 Testing & Verification

Sovereign enforces a strict **Data Correctness Suite** with CI gates for syntax, types, and math purity:

```bash
# Run the entire test suite
pytest tests/ -v

# Run logic & data integrity tests
pytest tests/test_logic_improvements.py -v

# Run type-checking on critical modules
mypy modules/scoring/ modules/retry_utils.py db/

# Run linter and formatting checks
ruff check .
```

The testing pyramid ensures:
- **Unit**: Logic and math purity (`test_logic_improvements.py`, `test_adapters_nse_xbrl.py`).
- **Contract**: Pydantic model validity and field normalization.
- **PIT & Regression**: Point-in-time non-leakage verification and structural alpha consistency.

---

## 🗂️ Project Structure
```
├── modules/               # Core domain logic, scoring, and data ingestion
│   ├── adapters/          # Source-specific fetchers (ScreenerIn, NSEXBRL, PNSEA, NSEPython, yFinance)
│   ├── data_layer/        # DataService orchestrator and provider fallback chain
│   ├── normalization/     # Data cleaning and DQ Gates
│   ├── risk/              # Return-based correlation & HRP allocation
│   ├── strategies/        # Quantitative strategies and factor models
│   └── models.py          # Pydantic v2 Contract Boundary
├── db/                    # SQLAlchemy 2.0 Persistence Layer & PIT Store
├── web-ui/                # Vite/React/TS Frontend Terminal
├── worker/                # Async background jobs and distributed workers
├── runtime/               # Local DB files and dynamic states (Git Ignored)
├── tests/                 # Unit, Contract, PIT, and Regression Tests
├── scripts/internal/      # QARP backtest engine, liquidity simulator, and debug scripts
├── sovereign_cli.py       # AUTHORITATIVE CLI ENTRY POINT
└── main.py                # FastAPI Web Application Entry Point
```

---
*Sovereign Terminal v4.3.0 — Precision Quantitative Equity Research & Data Integrity.*
