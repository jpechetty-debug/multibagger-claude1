# Sovereign Research Terminal v4.2.0
## // Institutional-Grade Quantitative Research & Data Integrity //

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![SQLite + DuckDB](https://img.shields.io/badge/Database-SQLite%20%2B%20DuckDB-orange.svg)]()
[![Pydantic v2](https://img.shields.io/badge/Validation-Pydantic%20v2-red.svg)]()
[![FastMCP](https://img.shields.io/badge/Agentic-FastMCP-green.svg)]()
[![Nexus Alpha](https://img.shields.io/badge/Nexus%20Alpha-v12.5-gold.svg)]()

Sovereign v4.2.0 is an advanced equity research platform designed for structural reliability and high-conviction quantitative signaling. It features a **hardened data quality pipeline**, **sigmoid-normalized scoring**, and **XGBoost-powered alpha signals** for a universe of 2,000+ Indian equity tickers.

> [!IMPORTANT]
> **Data Integrity First.** v4.2.0 introduces proactive Data Quality (DQ) gates and Pydantic boundary enforcement, ensuring that low-quality upstream data never corrupts your analytical models or trade signals.

---

## 🏗️ The Data Correctness Pipeline (Hardened)

To eliminate silent failures and scale-ambiguity errors, Sovereign implements a **5-Layer Hardening Architecture**:

1. **Ingestion Boundary**: Pydantic v2 models (`models.py`) with `extra="ignore"` and auto-scaling validators that detect and correct fraction-to-percent ambiguity (e.g., ROE 0.15 → 15.0%).
2. **Symbol Canonicalization**: Centralized utility (`symbol_utils.py`) that resolves exchange suffixes (`.NS`, `.BO`, `.N`, `.NSE`) into a single source of truth for DB storage.
3. **Data Quality (DQ) Gates**: Proactive physical-limit validators (`dq_gates.py`) that clamp metrics to realistic ranges (e.g., PE capped at 1000, Debt/Equity at 50) and generate DQ flags.
4. **Financial Adapter**: Decoupled extraction layer (`financial_adapter.py`) that maps messy upstream DataFrames into a typed `NormalizedFinancials` dataclass.
5. **Pure Math Engines**: Calculation modules (CAGR, ROE, F-Score) are now pure functions, making the core math 100% unit-testable without network dependencies.

---

## 🔍 Core Analytical Modules

### 1. The Compounding Lens (Sprint 1)
Deep analysis of structural growth and shareholder returns:
- **CAGR Purity**: 3Y and 5Y Revenue, PAT, and EPS CAGRs with a "Consistency" score.
- **Dividend Audit**: Yield and Payout analysis with automatic outlier capping.
- **SEBI Cap Classification**: Real-time classification into Large, Mid, Small, and Micro Cap categories.

### 2. Nexus Alpha v12.5 Scoring Engine
Dynamically weighted factors based on **Market Regime** (Bull/Bear/Sideways):
- **Growth (15%)**: Sigmoid-normalized Sales and EPS expansion.
- **Quality (15%)**: Average ROE (5Y) + Cashflow validation (CFO/PAT).
- **Risk (10%)**: Institutional-grade F-Score floor + Debt/Equity constraints.
- **ML Meta-Model**: Meta-scoring layer using XGBoost and SHAP for explainable AI alpha.

---

## ⚡ Analytical Performance (DuckDB Optimized)

Sovereign leverages a **SQLite + DuckDB** hybrid approach:
- **Lightning Queries**: Analytical sorting and filtering across 2,000+ records in <5ms.
- **PIT Auditing**: Point-In-Time fundamentals snapshots stored in SQLite for backtest accuracy.
- **Zero-Infra**: Native C++ extensions attached to the local SQLite storage.

---

## 🚀 Getting Started

### 1. Installation & Setup
```bash
# Clone and install
git clone https://github.com/your-repo/sovereign-terminal.git
cd sovereign-terminal
python -m venv .venv
source .venv/bin/activate  # Or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Initialize System
python sovereign_cli.py sys setup
python sovereign_cli.py db init
```

### 2. Operational Workflow
```bash
# Run a full universe scan (NSE stocks)
python sovereign_cli.py scan quick

# Train the ML Meta-Model
python sovereign_cli.py ml train

# Start the Web API (Port 9005)
uvicorn main:app --reload --port 9005
```

### 3. Critical Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `SOVEREIGN_API_KEY` | Production API Security | None (Required) |
| `SOVEREIGN_ENV` | Environment Context | `local` |
| `OLLAMA_MODEL` | LLM for Thesis Generation | `llama3.2:3b-instruct-fp16` |

---

## 🧪 Testing & Verification

Sovereign enforces a strict **Data Correctness Suite**:

```bash
# Run Data Integrity & Math Verification (42+ tests)
pytest tests/test_data_correctness.py -v

# Run Full Test Suite (excluding live network tests)
pytest tests/ -m "not live"
```

The testing pyramid ensures:
- **Unit**: Logic and math purity.
- **Contract**: Pydantic model validity.
- **Regression**: Structural alpha consistency across updates.

---

## 🗂️ Project Structure (v4.2)
```
├── modules/
│   ├── adapters/          # Source-specific fetchers (NSE, yFinance)
│   ├── normalization/     # Data cleaning and DQ Gates
│   ├── strategies/        # Allocation and HRP logic
│   ├── models.py          # Pydantic v2 Contract Boundary
│   ├── dq_gates.py        # Proactive physical-limit validators
│   └── financial_adapter.py # Clean financial data normalizer
├── db/
│   ├── repository.py      # SQLAlchemy 2.0 Persistence Layer
│   └── pit_auditor.py     # Point-In-Time snapshots
├── sovereign_cli.py       # AUTHORITATIVE ENTRY POINT
└── main.py                # FastAPI Web Application
```

---
*Sovereign Terminal v4.2.0 — Precision Quantitative Equity Research.*
