# Sovereign Research Terminal v4.4.0
## // Institutional-Grade Quantitative Research, Alpha Modeling & Data Integrity //

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![SQLite + DuckDB](https://img.shields.io/badge/Database-SQLite%20%2B%20DuckDB-orange.svg)]()
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)]()
[![React Vite](https://img.shields.io/badge/Frontend-React%20Vite-61dafb.svg)]()
[![XGBoost + SHAP](https://img.shields.io/badge/ML-XGBoost%20%2B%20SHAP-darkgreen.svg)]()
[![Celery + Redis](https://img.shields.io/badge/Workers-Celery%20%2B%20Redis-red.svg)]()
[![Pydantic v2](https://img.shields.io/badge/Validation-Pydantic%20v2-red.svg)]()
[![Nexus Alpha](https://img.shields.io/badge/Nexus%20Alpha-v12.5-gold.svg)]()

**Sovereign v4.4.0** is an enterprise-grade equity research and algorithmic alpha platform engineered for structural data correctness, rigorous Point-in-Time (PIT) backtesting, explainable machine learning, and high-conviction quantitative signaling across 2,000+ Indian equity tickers (NSE & BSE).

---

## 🌟 Key Capabilities & Architectural Highlights

```
                      ┌──────────────────────────────────────────────┐
                      │          SOVEREIGN TERMINAL v4.4.0           │
                      └──────────────────────┬───────────────────────┘
                                             │
      ┌────────────────────────┬─────────────┴────────────┬────────────────────────┐
      ▼                        ▼                          ▼                        ▼
┌──────────────┐      ┌─────────────────┐      ┌──────────────────────┐   ┌────────────────┐
│ Data Layer   │      │ Scoring Engine  │      │ ML Alpha & Explain   │   │ Execution & UI │
├──────────────┤      ├─────────────────┤      ├──────────────────────┤   ├────────────────┤
│ • 6-L Hardening│     │ • Nexus Alpha   │      │ • XGBoost Regressor  │   │ • FastAPI (9005)│
│ • SEBI PIT 60d │    │ • DuPont ROE 5-S│      │ • Binary Classifier  │   │ • React Vite   │
│ • Multi-Provider│   │ • Regime HMM    │      │ • SHAP TreeExplainer │   │ • CLI Suite    │
│ • Circuit Brkr│     │ • Sector Weights│      │ • Optuna Bayes Tuning│   │ • FastMCP Swarm│
└──────────────┘      └─────────────────┘      └──────────────────────┘   └────────────────┘
```

### 1. Hardened Data Correctness & PIT Integrity
- **SEBI Filing Lag Rules**: Enforces mandatory 45-day reporting lag for Q1–Q3 and **60-day lag for Q4 (March annual audited results)** via `pit_auditor.py` and `NSEXBRLProvider` to eliminate look-ahead bias.
- **PIT Hard Gate (`PITViolationError`)**: Real-time hard assertion preventing premature data usage before official dissemination, coupled with per-stock isolation in batch screeners.
- **Circuit Breakers**: Thread-safe `CLOSED → OPEN → HALF_OPEN` states (`modules/retry_utils.py`) protecting data ingestion from upstream rate limits and outages.
- **Sector-Aware Data Confidence**: Dynamic confidence scoring (e.g. Banking & Financial Services zeroing D/E weight `weights["w_de"] = 0.0` with exact 77.8% confidence calculation).
- **Multi-Provider Fallback**: Priority waterfall (`ScreenerInProvider` → `NSEXBRLProvider` → `PNSEAProvider` → `NSEPythonProvider` → `YFinanceProvider`).

### 2. Multi-Vector Scoring & Quantitative Research
- **Nexus Alpha (v12.5)**: Dynamic factor engine adjusting weights across Market Regimes (Bull / Bear / Sideways / High Volatility detected via Hidden Markov Models):
  - **Growth (15%)**: Sigmoid-normalized Sales & EPS expansion.
  - **Quality (15%)**: 5-Year Average ROE + Cash Flow Validation (CFO/PAT).
  - **Risk & Capital Structure (10%)**: Institutional-grade Piotroski F-Score + Debt/Equity bounds.
  - **Valuation & Value Gap**: Normalized PE, PEG, and Sector-Relative Median discounting.
- **DuPont ROE Decomposition (3-Stage & 5-Stage)**: Deconstructs return on equity into operational margins, asset velocity, leverage multipliers, tax burden, and interest burden for diagnostic clarity.
- **Turnaround CAGR Engine**: Mathematical recovery metrics (`_turnaround_growth`) for candidates rebounding from negative base earnings.
- **Return-Based Portfolio Risk**: Pearson correlation matrix computed on **daily percentage returns** (`close_prices.pct_change()`) in `modules/risk/correlation.py` to eliminate non-stationary price-level trend distortions.
- **Hierarchical Risk Parity (HRP)**: Conviction-weighted portfolio allocation and liquidity-gated slippage checks.

### 3. Explainable ML Alpha & Walk-Forward Validation
- **Two-Model ML Architecture**: Blended XGBoost Regressor (predicting forward alpha) + XGBoost Classifier (predicting multibagger probability) in `modules/scoring/ml_score.py`.
- **SHAP Dominance Guard**: `check_shap_dominance` ensures no single feature disproportionately dominates model decisions (>90% threshold), preventing signal collapse.
- **Optuna Hyperparameter Optimization**: Bayesian parameter exploration over learning rate, tree depth, subsample ratios, and L1/L2 regularization (`_OPTUNA_SEARCH_SPACE`).
- **Expanding-Window Walk-Forward Validation**: Out-of-sample validation framework with locked 2018–2020 holdout exclusion (`modules/scoring/walk_forward.py`).

### 4. Distributed Workers & Telemetry
- **Dual-Mode Task Bus**: Transparent switching between local `asyncio` dev worker and distributed `celery` broker in `worker/task_bus.py`.
- **Celery Beat Schedule**: Automated maintenance tasks including factor data freshness audits (`check_factor_data_freshness`) scheduled on dedicated queues.
- **Redis Pub/Sub WebSocket Engine**: Multi-worker live price streaming on `live:prices` with token/API key authentication for secure subscriber distribution.
- **Hybrid Caching Layer**: In-memory LRU + Redis distributed cache for sub-millisecond stock score retrieval.

---

## 🗂️ Project Structure

```
Newmultibagger-main/
├── app_routes/            # FastAPI route controllers (public, trading, ml, portfolio, regime)
├── backtest/              # Historical backtesting engines & walk-forward evaluators
├── core/                  # Observability, structured logging, and system telemetry
├── db/                    # SQLAlchemy 2.0 models, repository layer, DuckDB + SQLite pooling
├── legacy/                # Preserved legacy CLI & backtest utilities (isolated package)
├── modules/               # Core analytical & financial domain modules
│   ├── adapters/          # Source fetchers (Bhavcopy, NSE XBRL, Jugaad, YFinance)
│   ├── data_layer/        # DataService orchestrator, DQ gates, and connections
│   ├── financial_analysis.py # DuPont 3/5-stage decomposition & fundamental ratios
│   ├── intelligence/      # LLM engines, news sentiment, promoter & insider tracking
│   ├── portfolio/         # HRP allocation, capital simulator, exit engine, tax efficiency
│   ├── risk/              # Slippage, correlation matrix, regime HMM, stress testing
│   ├── scoring/           # Modular scoring package:
│   │   ├── engine.py      # calculate_institutional_score orchestrator & PIT gate
│   │   ├── factors.py     # Base score, factor breakdown, and sector confidence
│   │   ├── ml_score.py    # XGBoost meta-model, SHAP explainers, Optuna tuning
│   │   ├── utils.py       # Safe conversions, Spearman IC, and Sharpe metrics
│   │   ├── walk_forward.py# Expanding-window validation & holdout evaluations
│   │   └── weights.py     # Regime & sector weight configurations
│   ├── hybrid_scoring.py  # Self-replacing compatibility shim for ml_score
│   ├── models.py          # Pydantic v2 contract boundary
│   └── pit_auditor.py     # Point-in-time auditor & SEBI lag enforcement
├── ops/                   # Institutional ablation engines & sprint drivers
├── research/              # Quantitative research notebooks and super investor registry
├── scripts/               # Automation scripts (universe scanner, paper trade, setup)
├── tests/                 # 500+ comprehensive automated unit & regression tests
├── web-ui/                # High-performance Vite/React/TypeScript analytical terminal
├── worker/                # Celery application, Redis cache, and background task bus
├── sovereign_cli.py       # Authoritative command-line interface shim
├── report_generator.py    # Analyst report generation shim
└── main.py                # FastAPI web backend application
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites & Environment Setup

```powershell
# Navigate into the core application directory
cd d:\Tradeidesa\Multibagger-claude\Newmultibagger-main

# Create and activate Python virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1  # On Linux/macOS: source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Initialize Database & Run Diagnostics

```powershell
# Set up initial database tables and seed data
python sovereign_cli.py db init

# Run system health check
python sovereign_cli.py health
```

### 3. Launch Backend API Server

```powershell
uvicorn main:app --reload --port 9005
```
- **API Documentation**: [http://localhost:9005/docs](http://localhost:9005/docs)
- **Health Check**: [http://localhost:9005/api/health](http://localhost:9005/api/health)
- **Auth Header**: `X-API-Key: DEV_KEY_123`

### 4. Launch Web UI Terminal

```powershell
# Open a new terminal tab
cd web-ui
npm install
npm run dev
```
- **Web Terminal**: [http://localhost:3000](http://localhost:3000) (Proxies `/api` and `/ws` to port 9005)

---

## 💻 Operational CLI Workflows

The `sovereign_cli.py` is the unified command center for operational research:

| Command | Action |
|---------|--------|
| `python sovereign_cli.py scan quick` | Runs a rapid fundamental & technical scan over top liquid tickers |
| `python sovereign_cli.py scan full` | Executes complete universe scan across 2,000+ NSE/BSE stocks |
| `python sovereign_cli.py ml train` | Trains XGBoost classifier + regressor with walk-forward validation |
| `python sovereign_cli.py ml optuna` | Runs Bayesian hyperparameter optimization for ML meta-model |
| `python sovereign_cli.py rs ingest` | Ingests Relative Strength sector and momentum signals |
| `python sovereign_cli.py paper-trade` | Generates live paper trading recommendation signals |
| `python sovereign_cli.py backtest run` | Executes QARP institutional backtest strategy |

---

## 🧪 Testing & Verification

Sovereign maintains an exhaustive test suite with **100% pass rate** (~500+ tests) covering financial math, ML stability, data correctness, and API contracts:

```powershell
# Run the entire test suite
python -m pytest --tb=short -q

# Run specific domain test suites
python -m pytest tests/test_scoring_engine.py -v
python -m pytest tests/test_hybrid_scoring_walk_forward.py -v
python -m pytest tests/test_dupont_decomposition.py -v
python -m pytest tests/test_phase67_pit.py -v
python -m pytest tests/test_task_bus.py -v
```

---

## ⚙️ Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SOVEREIGN_ENV` | Runtime environment (`local`, `staging`, `production`) | `local` |
| `DATABASE_URL` | SQLAlchemy connection string | `sqlite:///multibaggers.db` |
| `REDIS_URL` | Redis URL for caching and Celery broker | `redis://localhost:6379/0` |
| `TASK_BUS_MODE` | Dispatch mode for background tasks (`asyncio` or `celery`) | `asyncio` |
| `NSE_XBRL_PIT_LAG_DAYS` | Standard quarterly filing lag (days) | `45` |
| `FACTOR_STALENESS_DAYS` | Threshold for stale macro/factor exposure data | `45` |

---

*Sovereign Research Terminal v4.4.0 — Engineered for Institutional Quantitative Excellence.*
