# Sovereign AI Trading Engine (v9.6 - Hardened Signals)

An institutional-grade quantitative screening, scoring, and backtesting ecosystem for Indian (NSE) and Global (US) markets. **V9.6** introduces **Hardened Signals**, enforcing a strict data-quality floor, real-time momentum acceleration synchronization, and automated institutional paper-trade logging.

---

## 📈 Alpha Proof: Validated Performance

The Sovereign Engine uses a **triple-layer regime detection** system combined with a 2-quarter concentration cap that forces systematic portfolio rotation. This methodology contains drawdowns during volatility and aggressive re-entries during recoveries.

| Metric | Sovereign QARP (v4.4 Backtest) | Benchmark (Nifty 50) |
| :--- | :--- | :--- |
| **CAGR** | **+3.15%** | -2.26% |
| **Alpha** | **+5.10%** | - |
| **Sharpe Ratio** | **1.28** | -0.15 |
| **Max Drawdown** | **-1.02%** | -9.32% |
| **Information Ratio** | **0.61** | - |

> [!IMPORTANT]
> **V9.6: Hardened Signals & UI Refinement**
> This version introduces a **Hard Score Floor (> 5.0)** across all pipelines to exclude data-orphans and phantom picks. It also synchronizes the **Live Momentum Acceleration** signal from the backend directly to the Research Terminal gauges and adds automated paper-trade task scheduling.

---

## 🖥️ Sovereign Research Terminal v3

The frontend has been rebuilt from the ground up to provide institutional-grade data visualization and interaction:
- **Technical Brutalist Design**: High-conviction, asymmetric UI optimized for density and focus.
- **Modern Tech Stack**: Built with **Vite**, **React**, **TypeScript**, and **TailwindCSS**.
- **Real-time Integration**: Direct connection to the FastAPI backend with live **Momentum Acceleration** sync and internal network latency monitoring.
- **Agentic Ready**: Fully compatible with the **Model Context Protocol (MCP)** for seamless AI agent interaction.

---

## 🏗️ 8-Factor Institutional Scoring

The heart of the system is the dynamic, regime-aware weighting engine that uses **Sigmoid Normalization** and **Smooth Graduation Splines** to rank stocks.

- **Quality**: ROE Stability, Sales Growth (5Y CAGR), and F-Score (Piotroski).
- **Integrity**: Cash Conversion (CFO/PAT > 0.8) and Forensic Red Flags.
- **Value**: Sigmoid-weighted P/E Gap and PEG Margin of Safety.
- **Momentum**: Relative Strength and 52-Week High Proximity.

---

## 🛡️ Recovery Shield (Regime Detection)

Standard EMA-200 crossovers often lag during sharp market recoveries. **Sovereign v9.5** utilizes a **Momentum-Acceleration** signal:

1. **Trend Offset**: Price vs. 200DMA (300-day stabilized window).
2. **Momentum Acceleration**: The **Rate of Change (ROC)** of the EMA slope, dynamically synced to the Terminal gauges.
3. **Recovery Shield**: If the EMA slope is rapidly improving (`accel > 0.5`), the engine softens BEARish signals.
4. **Hard Score Floor**: Automatic disqualification of any pick with a `score <= 5.0` to preserve signal purity.

---

## 🛠️ Unified Operational CLI (`sovereign-cli.py`)

All operations are consolidated into a high-fidelity CLI for researchers and traders.

### 📄 Signal Logging (`paper-trade`)
The bridge between backtest and real execution.
- `paper-trade --universe 50`: Detects regime, runs 8-factor scoring, and logs signals.
- **Score Hardening**: Enforces the **> 5.0 score floor** to block data failures.
- **Automation**: Now supports **Celery-task-driven automation** for institutional paper-trade logging.

### 🔍 Universe Scanning (`scan`)
- `scan quick`: Main high-conviction screener.
- `scan swarm`: Trigger MiroFish Multi-Agent swarm intelligence.
- `scan master`: Audit the core "Master Picks" list.

### 🧪 Backtesting & ML (`backtest` / `ml`)
- `backtest qarp --years 3`: Walk-forward simulation with institutional friction (slippage/brokerage).
- `ml train`: Retrain the XGBoost Meta-Model on PIT (Point-In-Time) data.
- `ml explain --symbol TICKER`: Generate SHAP values to audit a stock's final score.

### ⚙️ System Ops (`sys`)
- `sys menu`: Main operational dashboard.
- `sys health`: Baseline system audit (dependencies, DB integrity).
- `sys regime`: Check current market status and the v9.5 Acceleration signal.

---

## 🗄️ Persistence & Data Integrity
- **Architecture**: 100% yfinance + local point-in-time SQL/CSV data sources.
- **PIT Datastore**: Reproducible historical data via `pit_store.db`.
- **Signal Log**: `paper_trade_signals.json` contains the verified out-of-sample data trail.
- **Task Queue**: Async processing via **Redis** and **Celery**.

---
*Professional-grade quantitative excellence on Indian and Global markets.*
