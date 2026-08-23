# Sovereign Research Terminal v4.4.0

> **Institutional Alpha Architecture: Quantitative Equity Research, Explainable Machine Learning & Agentic Intelligence**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![SQLite + DuckDB](https://img.shields.io/badge/Database-SQLite%20%2B%20DuckDB-orange.svg)]()
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)]()
[![React Vite](https://img.shields.io/badge/Frontend-React%20Vite-61dafb.svg)]()
[![XGBoost + SHAP](https://img.shields.io/badge/ML-XGBoost%20%2B%20SHAP-darkgreen.svg)]()
[![Celery + Redis](https://img.shields.io/badge/Workers-Celery%20%2B%20Redis-red.svg)]()
[![Nexus Alpha](https://img.shields.io/badge/Nexus%20Alpha-v12.5-gold.svg)]()

The **Sovereign Research Terminal** is an enterprise-grade quantitative equity research platform built for systematic stock screening, Point-in-Time (PIT) backtesting, explainable AI alpha discovery, and portfolio risk management across 2,000+ Indian equity tickers (NSE & BSE).

---

## 🚀 Navigation & Application Codebase

The core application codebase, API backend, web UI, analytical engines, and worker infrastructure are located in:

👉 **[Newmultibagger-main/](./Newmultibagger-main/)** *(See [Newmultibagger-main/README.md](./Newmultibagger-main/README.md) for full technical documentation).*

---

## 🏗️ Core Architecture & System Modules

- **9-Vector Nexus Alpha (v12.5)**: Dynamic factor engine adjusting weights across Market Regimes (Bull / Bear / Sideways / High Volatility detected via Hidden Markov Models).
- **DuPont ROE 3-Stage & 5-Stage Decomposition**: Deep fundamental profitability attribution analyzing Net Margin, Asset Turnover, Financial Leverage, Tax Burden, and Interest Burden.
- **Explainable ML Meta-Model (XGBoost + SHAP)**: Two-model architecture (Classifier + Regressor) with Optuna Bayesian hyperparameter optimization, SHAP TreeExplainer feature dominance checks, and Expanding-Window Walk-Forward Validation.
- **Hardened PIT & Data Integrity Engine**: Dynamic SEBI filing lag rules (60 days for Q4 March annual results, 45 days for Q1–Q3) with `PITViolationError` hard gates preventing look-ahead bias in backtests.
- **Sector-Specific Factor Normalization**: Sector-aware weighting (e.g. Banking & Financial Services zeroing D/E `weights["w_de"] = 0.0` with exact 77.8% confidence calculation).
- **Multi-Provider Data Waterfall**: Redundant fallback chain (`ScreenerInProvider` → `NSEXBRLProvider` → `PNSEAProvider` → `NSEPythonProvider` → `YFinanceProvider`).
- **Return-Based Risk Correlation**: Pearson correlation computed on daily percentage returns to eliminate non-stationary price level distortions.
- **Distributed Worker Bus**: Unified task bus supporting local `asyncio` loop and distributed `celery` broker with Redis caching and automated Celery Beat maintenance schedules.
- **Unified Operational CLI**: `sovereign_cli.py` for universe scanning, ML training, RS signal ingestion, and backtesting.

---

## ⚡ Quick Start

```powershell
# 1. Navigate to core app directory
cd Newmultibagger-main

# 2. Setup environment & dependencies
python -m venv .venv
.venv\Scripts\Activate.ps1  # On Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 3. Initialize database & run diagnostics
python sovereign_cli.py db init
python sovereign_cli.py health

# 4. Run test suite (100% pass rate)
python -m pytest --tb=short -q

# 5. Start FastAPI Backend Server
uvicorn main:app --reload --port 9005

# 6. In a separate terminal tab: Start Vite React UI
cd web-ui
npm install
npm run dev
```

- **Frontend Terminal**: `http://localhost:3000` (or `http://localhost:5173`)
- **Backend API**: `http://localhost:9005`
- **Swagger Docs**: `http://localhost:9005/docs`
- **API Key Header**: `X-API-Key: DEV_KEY_123` (or query parameter `?token=DEV_KEY_123`)

---

## 📊 Knowledge Graph & Architectural Blueprint

- **Graphify Knowledge Graph**: AST-indexed knowledge graph containing **20,864 nodes, 40,087 edges, and 1,119 communities** in `graphify-out/`.
- **CodeGraph Intelligence**: Comprehensive semantic symbols and call paths index across **504 files (7,027 nodes, 15,037 edges)** in `.codegraph/`.
- **System Blueprint**: Detailed module maps, data flows, and design rules documented in [.agent/ARCHITECTURE.md](./.agent/ARCHITECTURE.md).

---

*Sovereign Research Terminal v4.4.0 — Precision Quantitative Equity Research & Data Integrity.*
