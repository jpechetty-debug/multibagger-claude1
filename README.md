# Sovereign Research Terminal

> **Institutional Alpha Architecture: Quantitative Equity Research & Agentic Intelligence**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![SQLite + DuckDB](https://img.shields.io/badge/Database-SQLite%20%2B%20DuckDB-orange.svg)]()
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)]()
[![React Vite](https://img.shields.io/badge/Frontend-React%20Vite-61dafb.svg)]()
[![Nexus Alpha](https://img.shields.io/badge/Nexus%20Alpha-v12.5-gold.svg)]()

The **Sovereign Research Terminal** is a high-performance quantitative research platform designed for systematic equity scoring, point-in-time (PIT) auditing, portfolio optimization, and machine learning alpha discovery across 2,000+ Indian equity tickers.

---

## 🚀 Navigation

The core application codebase, API backend, web UI, and scoring engines are located in:

👉 **[Newmultibagger-main/](./Newmultibagger-main/)** *(See [Newmultibagger-main/README.md](./Newmultibagger-main/README.md) for full technical documentation).*

---

## 🏗️ Key Architecture & Features

- **9-Vector Nexus Alpha (v12.5)**: Dynamic factor scoring adjusting to HMM-detected market regimes (Bull / Bear / Sideways).
- **Multi-Provider Data Adapter Layer**: Redundant fallback chain (`ScreenerInProvider` → `NSEXBRLProvider` → `PNSEAProvider` → `NSEPythonProvider` → `YFinanceProvider`).
- **Official NSE Integrated Filing (XBRL) Parser**: Audited balance sheet figures, TTM Sales/EPS growth, Debt/Equity, Book Value, and ROE%.
- **Hardened PIT & Data Integrity Engine**: SEBI quarter-sensitive filing lag rules (60 days for Q4 March annual results, 45 days for Q1–Q3) to prevent look-ahead bias in backtests.
- **Return-Based Portfolio Risk Correlation**: Pearson correlation computed on daily percentage returns to eliminate non-stationary price level distortions.
- **Turnaround CAGR Recovery Engine**: Mathematical recovery scoring for turnaround candidates recovering from negative base earnings.
- **Agentic AI & FastMCP**: Integrated FastMCP server with persistent Research Memory and Swarm Intelligence.
- **Unified Operational CLI**: `sovereign_cli.py` for universe scanning, ML training, RS signal ingestion, and strategy backtesting.

---

## 📊 Knowledge Graph & Codebase Structure

- **Graphify Knowledge Graph**: AST-indexed graph containing **20,134 nodes, 38,650 edges, and 1,052 communities** in `graphify-out/`.
- **System Architecture**: Detailed in [.agent/ARCHITECTURE.md](./.agent/ARCHITECTURE.md).

---

## ⚡ Quick Start

```bash
# Navigate to core app directory
cd Newmultibagger-main

# Setup environment & dependencies
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Run full test suite
pytest tests/ -v

# Start FastAPI API server
uvicorn main:app --reload --port 9005

# In a separate terminal tab: Start Vite React UI
cd web-ui
npm install
npm run dev
```

---
*For in-depth module documentation, operational workflows, and environment configurations, read [Newmultibagger-main/README.md](./Newmultibagger-main/README.md).*
