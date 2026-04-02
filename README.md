# 🏛️ Sovereign AI Trading Engine (v4.0 - Institutional Grade)

An institutional-grade quantitative screening, scoring, and backtesting ecosystem designed for the Indian (NSE) and Global (US) markets. V4.0 introduces the **QARP Alpha Validation Suite**, a unified **Sovereign CLI**, and automated **Cold-Start Setup**.

---

## 🚀 Quick Start (Cold Start)

To initialize the environment, database, and baseline models in a single command:

```bash
python setup.py
```
This script handles `.env` configuration, database schema migrations, and fetches initial benchmark data for Nifty 50 calibration.

---

## 🧠 Hardened Scoring Methodology: The 8-Factor Model

The heart of the system is the `calculate_institutional_score` function in `modules/scoring.py`. This is a dynamic, regime-aware weighting engine that uses **Sigmoid Normalization** and **Smooth Graduation Splines** to ensure stable, bias-free rankings.

| Factor | Default Weight | Why it Matters |
| --- | --- | --- |
| **Sales Growth** | 0.15 | Verifies top-line demand expansion (5Y CAGR). |
| **ROE Stability** | 0.15 | Measures capital efficiency and moat strength (5Y Average). |
| **Cash conversion** | 0.10 | Detects accounting red flags (CFO/PAT > 0.8). |
| **Valuation Gap** | 0.15 | Graham / PEG Margin of Safety. |
| **EPS Velocity** | 0.10 | Identifies profit inflection points. |
| **F-Score** | 0.10 | 9-Pt Piotroski business health. |
| **Leverage** | 0.10 | Debt/Equity penalties (Sect-weighted). |
| **Momentum** | 0.15 | Relative Strength and 52W High proximity. |

---

## 📈 Alpha Validation (Backtesting)

V4.0 introduces the **QARP Walk-Forward Backtester**, allowing you to validate the 8-factor thesis against historical Point-In-Time (PIT) fundamentals.

```bash
python sovereign-cli.py backtest qarp --years 3 --universe top-100
```
- **PIT Methodology**: Simulates historical reporting lags to eliminate look-ahead bias.
- **Benchmark Comparison**: Automatic Alpha calculation vs. Nifty 50 (^NSEI).
- **Report Generation**: Detailed Markdown reports with CAGR, Sharpe, and Drawdown metrics.

---

## 🛠️ Unified Operational CLI (`sovereign-cli.py`)

The root directory has been consolidated. All specialized scripts are now accessible through a unified command structure:

### 🗄️ Database (`db`)
- `db init`: Initialize/migrate schemas.
- `db stats`: Instant table audit and row counts.
- `db cleanup`: Vacuum and optimize all SQLite databases.

### 🔍 Universe Scanning (`scan`)
- `scan quick`: Main high-conviction screener run.
- `scan master`: Audit the core "Master Picks" list.
- `scan swarm`: Trigger MiroFish Multi-Agent simulation for symbols.
- `scan user`: Custom watch-list scanner.

### 🔬 Research & ML (`research` / `ml`)
- `ml train`: Retrain the XGBoost Meta-Model on PIT data.
- `ml explain --symbol TICKER`: Generate SHAP values for a specific stock's score.
- `research alpha`: Calculate historical alpha attribution.
- `research liquidity`: Run slippage simulations for large positions.

---

## 🏗️ System Architecture

The trading engine follows a decoupled, **Service-Oriented Design**:

1. **Ingestion**: Multi-source data fetchers (yfinance/local) with Pydantic validation.
2. **Scoring**: 8-Factor regime-aware engine + XGBoost Meta-Model.
3. **Execution**: Slippage-aware order simulation with VIX-based Circuit Breakers.
4. **Audit**: PIT DataStore ensures every historical tick is reproducible.

---

## 🛡️ Reliability & Security
- **Parameterized SQL**: 100% protection against injection in all DB layers.
- **Circuit Breakers**: VIX > 35 automatic "Hard Kill" switch for production scanners.
- **Standardized API**: FastAPI backend with `HTTPException` standardized error codes.

---
*Institutional-grade quantitative excellence on Indian and Global markets.*
