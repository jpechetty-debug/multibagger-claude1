# Sovereign AI Trading Engine (v11.0 - Nexus Alpha)

An institutional-grade quantitative screening, scoring, and backtesting ecosystem for Indian (NSE) and Global (US) markets. **V11.0** introduces **Nexus Alpha**, a major evolution that integrates **Multi-Agent Swarm Intelligence (MiroFish)** and **Real-Time News Sentiment** as a first-class alpha generator.

---

## 📈 Alpha Proof: Validated Performance

The Sovereign Engine uses a **triple-layer regime detection** system combined with a 2-quarter concentration cap. **V11.0** adds a qualitative filter (Sentiment) to prune "Value Traps" that quantitative data alone might miss.

| Metric | Sovereign QARP (v4.4 Backtest) | Benchmark (Nifty 50) |
| :--- | :--- | :--- |
| **CAGR** | **+3.15%** | -2.26% |
| **Alpha** | **+5.10%** | - |
| **Sharpe Ratio** | **1.28** | -0.15 |
| **Max Drawdown** | **-1.02%** | -9.32% |

> [!IMPORTANT]
> **V11.0: Nexus Alpha & Swarm Intelligence**
> This version introduces a **9th Factor** to the scoring model: **News Sentiment**. It also integrates the **MiroFish Multi-Agent Engine**, which initiates a real-time debate between AI agents (Fundamentalist, Technicalist, Skeptic) to validate high-conviction picks before execution.

---

## 🖥️ Sovereign Research Terminal v3.5

The frontend now provides deeper observability into the AI decision process:
- **News Feed Integration**: Real-time headline analysis and sentiment "drift" monitoring via `/api/news`.
- **Swarm Consensus Reports**: View full markdown reports from the MiroFish agent debates via `/api/swarm/report`.
- **High-Fidelity Sync**: Actual network latency monitoring and system heartbeat integration.

---

## 🏗️ 9-Factor Institutional Scoring (v11.0)

The heart of the system is a dynamic, regime-aware weighting engine that now correlates quant metrics with qualitative market consensus.

- **Quality**: ROE Stability, Sales Growth (5Y CAGR), and F-Score (Piotroski).
- **Integrity**: Cash Conversion (CFO/PAT > 0.8) and Forensic Red Flags.
- **Value**: Sigmoid-weighted P/E Gap and PEG Margin of Safety.
- **Momentum**: Relative Strength and 52-Week High Proximity.
- **Nexus Alpha (New)**: **Real-Time News Sentiment**. Uses NLP (VADER) to score headlines and detect institutional "Toxic Drift" or "Breakout Bullishness."

---

## 🐟 MiroFish Swarm Intelligence (v10.0)

High-conviction picks are passed through a **Multi-Agent Simulation Bridge**:
1. **Context Generation**: Real-time SQL extraction of all QARP metrics.
2. **Agent Debate**: A swarm of specialized agents deliberates on the "Fundamental vs. Qualitative" alignment.
3. **Consensus Report**: Generates a high-fidelity markdown thesis for every pick in the Top 10.

---

## 🛡️ Recovery Shield (Regime Detection)

Standard EMA-200 crossovers are augmented by a **Momentum-Acceleration** signal:
1. **Trend Offset**: Price vs. 200DMA (300-day stabilized window).
2. **Momentum Acceleration**: The **Rate of Change (ROC)** of the EMA slope.
3. **Recovery Shield**: Rapid slope improvement (`accel > 0.5`) triggers a "Bullish Inflection" offset for BEARish signals.

---

## 🛠️ Unified Operational CLI (`sovereign_cli.py`)

### 📄 Signal Logging (`paper-trade`)
- `paper-trade --universe 50`: Runs 9-factor scoring and logs signals for quarterly rebalancing.

### 🔍 Universe Scanning (`scan`)
- `scan quick`: Main high-conviction quantitative screener.
- `scan swarm`: **v10.0** - Trigger MiroFish swarm intelligence for target tickers.
- `scan swarm --deep --push`: Run a high-fidelity simulation and push conviction updates to the DB.

### 🧪 Backtesting & ML (`backtest` / `ml`)
- `backtest qarp --rebalance quarterly`: Walk-forward simulation with institutional friction.
- `ml explain --symbol TICKER`: Generate SHAP values to audit a stock's final score.

### ⚙️ System Ops (`sys`)
- `sys db dups`: Scan database for duplicate records.
- `sys regime`: Check current market status and the v9.6+ Acceleration signal.

---

## 🗄️ Persistence & Data Integrity
- **Datastore**: SQLite (`stocks.db`) + PIT historical data (`pit_store.db`).
- **Signal Log**: `paper_trade_signals.json` contains the verified out-of-sample data trail.
- **Swarm Repository**: `data/swarm_reports/` stores all MiroFish consensus reports.

---
*Professional-grade quantitative excellence on Indian and Global markets.*
