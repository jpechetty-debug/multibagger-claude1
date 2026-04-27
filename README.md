# Sovereign Research Terminal v4.0.0
## // The Sovereign Hybrid: Institutional Alpha Architecture //

Sovereign v4.0.0 represents a significant technical debt remediation and architectural leap. It integrates a **Modular Data Service (v4.0)**, a **Sigmoid-Normalized Nexus Alpha (v12.0)** scoring engine, and a **SQLite + DuckDB Hybrid** analytical layer for institutional-grade research.

> [!IMPORTANT]
> **Sovereign is built for reliability.** v4.0.0 introduces a modular adapter layer, hard-fail security dependencies, and a robust Celery worker architecture that eliminates event-loop anti-patterns.

---

## 🏗️ v4.0 Architecture: Modular & Resilient

The "God-Module" technical debt has been eliminated. The system is now decomposed into specialized layers:

### 1. Modular Data Service (`modules/data_service.py`)
Orchestrates data fetching through a prioritized fallback chain:
- **`modules/adapters/nse.py`**: High-fidelity PNSEA and NSEPython adapters.
- **`modules/adapters/yfinance.py`**: Robust yfinance fallback with fast-info recovery.
- **`modules/normalization/cleaner.py`**: Centralized data quality gates and skeletal payload detection.

### 2. Security & Resource Hub
- **`modules/auth.py`**: Hard-fail `SOVEREIGN_API_KEY` enforcement. REFUSES to start if not configured.
- **`modules/connections.py`**: Centralized SQLite WAL-mode management and I/O semaphores.
- **`modules/cache.py`**: High-speed in-memory TTL caching for market regimes and sector medians.

### 3. ML-Ops & Meta-Scoring
- **`scripts/train_hybrid_model.py`**: Reproducible XGBoost training entry point.
- **`models/schema.json`**: Feature contract documentation for the forward-return meta-model.
- **`modules/hybrid_scoring.py`**: Decoupled ML inference layer with data-fetching isolation.

---

## 🔬 Scoring Protocol: Nexus Alpha v12.0

Every stock is audited across nine distinct vectors, dynamically weighted by **Market Regime**:

| Factor | Description | Weight (Balanced) |
|--------|-------------|-------------------|
| **Growth** | 5Y Sales and EPS Expansion | 15% |
| **Quality** | ROE/ROCE splines + Asset-Light CFO/PAT | 15% |
| **Value** | Sigmoid-normalized sector-relative PE/PEG | 15% |
| **Momentum** | Composite RS + 52-Week High Proximity | 10% |
| **Risk** | Institutional F-Score floor + D/E Constraints | 10% |

---

## ⚡ Analytical Performance (DuckDB Optimized)

Sovereign v4.0.0 continues the **SQLite + DuckDB** hybrid approach for lightning-fast quantitative research.
- **Sorting 2k Tickers**: <5ms (Vectorized SIMD)
- **Historical Aggregation**: ~30ms (In-memory OLAP)
- **Zero Infrastructure**: Native C++ extensions attached to the SQLite file.

---

## 🚀 Operations & Deployment

### Quickstart (Local)
```bash
# 1. Start Backend (Port 9005)
uvicorn main:app --reload --port 9005

# 2. Start Worker (Celery)
celery -A worker.celery_app worker --loglevel=info

# 3. Start Frontend
cd web-ui && npm run dev
```

### Critical Environment Variables
| Variable | Purpose | Default |
|----------|---------|---------|
| `SOVEREIGN_API_KEY` | REQUIRED in production | None (Fails if missing) |
| `SOVEREIGN_ENV` | `production` / `local` | `local` |
| `SOVEREIGN_RELOAD` | Enable uvicorn auto-reload | `false` |
| `OLLAMA_MODEL` | LLM model for thesis gen | `llama3.2:3b-instruct-fp16` |

---

## 🧪 Testing Suite

Sovereign v4.0.0 enforces a strict **Testing Pyramid**:

1. **Unit Tests**: `pytest -m "not live"` — Logic and math validation.
2. **E2E Integration**: `pytest tests/e2e_scoring_pipeline.py` — Verifies full Fetch -> Score -> Result pipe.
3. **Frontend (Vitest)**: `npm test` inside `web-ui`.
4. **CI Pipeline**: GitHub Actions enforces Lint (Ruff), Types (Mypy), and Syntax Parsing.

---

## 🗂️ File Landscape (v4.0)
```
├── modules/
│   ├── adapters/          # Source-specific data fetchers
│   ├── normalization/     # Data cleaning and quality gates
│   ├── auth.py            # Security dependencies
│   ├── connections.py     # DB & I/O Orchestration
│   ├── cache.py           # In-memory volatile state
│   ├── data_utils.py      # Sync/Async compatibility layers
│   └── hybrid_scoring.py  # ML Meta-Model inference
├── scripts/
│   ├── internal/          # Core operational scripts
│   └── train_hybrid_model.py # ML training canonical entry
└── worker/
    └── tasks.py           # Hardened Celery task definitions
```

---

*Sovereign Terminal v4.0.0 — Built for structural alpha.*
