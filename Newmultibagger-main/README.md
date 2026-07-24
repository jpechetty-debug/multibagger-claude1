# Sovereign Research Terminal v4.2.0
## // Institutional-Grade Quantitative Research & Data Integrity //

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![SQLite + DuckDB](https://img.shields.io/badge/Database-SQLite%20%2B%20DuckDB-orange.svg)]()
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)]()
[![React Vite](https://img.shields.io/badge/Frontend-React%20Vite-61dafb.svg)]()
[![Pydantic v2](https://img.shields.io/badge/Validation-Pydantic%20v2-red.svg)]()
[![Nexus Alpha](https://img.shields.io/badge/Nexus%20Alpha-v12.5-gold.svg)]()

Sovereign v4.2.0 is an advanced equity research platform designed for structural reliability and high-conviction quantitative signaling. It features a **hardened data quality pipeline**, **sigmoid-normalized scoring**, and **XGBoost-powered alpha signals** for a universe of 2,000+ Indian equity tickers.

> [!IMPORTANT]
> **Data Integrity First.** v4.2.0 introduces proactive Data Quality (DQ) gates, Circuit Breakers, and Pydantic boundary enforcement, ensuring that low-quality upstream data never corrupts analytical models or trade signals. **Alpha Vantage dependencies have been completely removed** in favor of a pure `yfinance` and local NSE data architecture.

---

## 🏗️ The Data Correctness Pipeline (Hardened)

To eliminate silent failures and scale-ambiguity errors, Sovereign implements a **5-Layer Hardening Architecture**:

1. **Ingestion Boundary**: Pydantic v2 models (`modules/models.py`) with `extra="ignore"` and auto-scaling validators that detect and correct fraction-to-percent ambiguity (e.g., ROE 0.15 → 15.0%).
2. **Circuit Breakers**: Thread-safe `CLOSED → OPEN → HALF_OPEN` state machines (`modules/retry_utils.py`) for resilient data ingestion from `yfinance` and `nse`.
3. **Data Quality (DQ) Gates**: Proactive physical-limit validators (`modules/dq_gates.py`) that clamp metrics to realistic ranges (e.g., PE capped at 1000) and generate DQ flags.
4. **Financial Adapter**: Decoupled extraction layer (`modules/financial_adapter.py`) that maps messy upstream DataFrames into typed `NormalizedFinancials`.
5. **Pure Math Engines**: Calculation modules (CAGR, ROE, F-Score) are now pure functions, making the core math 100% unit-testable without network dependencies.

---

## 🔍 Core Analytical Modules

### 1. The Compounding Lens
Deep analysis of structural growth and shareholder returns:
- **DuPont ROE Decomposition**: Breaks down ROE into Net Margin, Asset Turnover, and Financial Leverage.
- **CAGR Purity**: 3Y and 5Y Revenue, PAT, and EPS CAGRs with a "Consistency" score.
- **Earnings Velocity**: Linear regression of net margins across quarters.
- **Friction-Aware Liquidity Gate**: Pre-trade slippage rejection for illiquid micro-caps.

### 2. Nexus Alpha v12.5 Scoring Engine
Dynamically weighted factors based on **Market Regime** (Bull/Bear/Sideways detected via HMM classifier):
- **Growth (15%)**: Sigmoid-normalized Sales and EPS expansion.
- **Quality (15%)**: Average ROE (5Y) + Cashflow validation (CFO/PAT).
- **Risk (10%)**: Institutional-grade F-Score floor + Debt/Equity constraints.
- **ML Meta-Model**: Meta-scoring layer using XGBoost and SHAP for explainable AI alpha.

### 3. Quantitative Strategies & Signals
- **Sector-Relative Filtering**: Evaluates ROE/Growth/PE against sector medians.
- **Sector-Wise RS Ingestion**: Automated ingestion of high-conviction signals from Relative Strength (RS) screens into the database.
- **HRP Portfolio Allocation**: Hierarchical Risk Parity portfolio construction based on signal conviction.

---

## ⚡ Architecture & Performance

Sovereign leverages a **SQLite + DuckDB + PostgreSQL** approach:
- **Canonical DB Layer**: `db/engine.py` supports local SQLite testing and production PostgreSQL/TimescaleDB via `DATABASE_URL`.
- **Lightning Queries**: Analytical sorting and filtering across 2,000+ records via DuckDB in <5ms.
- **Point-In-Time (PIT) Auditing**: Fundamentals snapshots stored systematically to prevent forward-looking bias in backtests.
- **Technical Brutalist UI**: High-performance, Vite-powered React/TypeScript terminal interface.

---

## 🚀 Getting Started

### 1. Installation & Setup
```bash
# Clone and install backend
git clone https://github.com/your-repo/sovereign-terminal.git
cd sovereign-terminal
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Initialize System via CLI
python sovereign_cli.py sys setup
python sovereign_cli.py db init
```

### 2. Start the Backend API
The FastAPI server is the only active web backend entry point.
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

### Critical Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `SOVEREIGN_API_KEY` | Production API Security | None (Required) |
| `SOVEREIGN_ENV` | Environment Context | `local` |
| `DATABASE_URL` | SQLAlchemy Connection URL | `sqlite:///multibaggers.db` |
| `REDIS_URL` | Redis cache/Celery broker | `redis://localhost:6379/0` |

---

## 🧪 Testing & Verification

Sovereign enforces a strict **Data Correctness Suite** with CI gates for syntax, types, and math purity:

```bash
# Run the entire test suite (excluding live network requests)
pytest tests/ -m "not live" -v

# Run type-checking on critical modules
mypy modules/scoring/ modules/retry_utils.py db/

# Run linter and formatting checks
ruff check .
```

The testing pyramid ensures:
- **Unit**: Logic and math purity.
- **Contract**: Pydantic model validity.
- **Regression**: Structural alpha consistency across updates.

---

## 🗂️ Project Structure
```
├── modules/               # Core domain logic, scoring, and data ingestion
│   ├── adapters/          # Source-specific fetchers (NSE, yFinance)
│   ├── normalization/     # Data cleaning and DQ Gates
│   ├── strategies/        # Quantitative strategies and allocation
│   └── models.py          # Pydantic v2 Contract Boundary
├── db/                    # SQLAlchemy 2.0 Persistence Layer & PIT Auditors
├── web-ui/                # Vite/React/TS Frontend Terminal
├── worker/                # Async background jobs and distributed workers
├── runtime/               # Local DB files and dynamic states (Git Ignored)
├── tests/                 # Unit, Contract, and Regression Tests
├── scripts/internal/      # Maintenance and debug scripts
├── sovereign_cli.py       # AUTHORITATIVE CLI ENTRY POINT
└── main.py                # FastAPI Web Application Entry Point
```

---
*Sovereign Terminal v4.2.0 — Precision Quantitative Equity Research.*
