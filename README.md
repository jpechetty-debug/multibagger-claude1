# Sovereign AI Trading Engine (v4.4 - Regime-Aware)

An institutional-grade quantitative screening, scoring, and backtesting ecosystem for Indian (NSE) and Global (US) markets. V4.4 introduces **stabilized EMA-200** (300-day history), **concentration caps** (2-quarter max hold), and **regime-aware position sizing** with HMM + Dual EMA + Volatility filters.

---

## Alpha Proof: Validated Performance (v4.4)

The QARP 8-factor model is paired with a **triple-layer regime detection** system (HMM, EMA-50/200, 20-day rolling volatility) and a **concentration cap** that forces portfolio rotation every 2 quarters. Exposure scales from 10% (Bear) to 100% (Bull).

| Metric | Sovereign QARP (v4.4) | Benchmark (Nifty 50) |
| :--- | :--- | :--- |
| **CAGR** | **+3.15%** | -2.26% |
| **Alpha** | **+5.10%** | - |
| **Sharpe Ratio** | **1.28** | -0.15 |
| **Max Drawdown** | **-1.02%** | -9.32% |
| **Information Ratio** | **0.61** | - |

The Feb 2026 crash (-9.32% on Nifty) was contained to **-1.02%**. The concentration cap forces stock rotation, proving the model's alpha is systematic rather than single-stock dependent.

---

## 🚀 Quick Start (Cold Start)

To initialize the environment, database, and baseline models in a single command:

```bash
python setup.py
```
**V4.1 Enhancements**:
- **PIT Seeding**: Automatically populates `pit_store.db` with sample historical data for RELIANCE and TCS.
- **ML Cold-Start**: New clones can now run `ml train` immediately using seeded PIT data.

---

## 🧠 Hardened Scoring Methodology: The 8-Factor Model

The heart of the system is the `calculate_institutional_score` function in `modules/scoring.py`. This is a dynamic, regime-aware weighting engine that uses **Sigmoid Normalization** and **Smooth Graduation Splines**.

| Factor | Weight | Why it Matters |
| --- | --- | --- |
| **Sales Growth** | 0.15 | Verifies top-line demand expansion (5Y CAGR). |
| **ROE Stability** | 0.15 | Measures capital efficiency and moat strength (5Y Average). |
| **Cash conversion** | 0.10 | Detects accounting red flags (CFO/PAT > 0.8). |
| **Valuation Gap** | 0.15 | Graham / PEG Margin of Safety. |
| **EPS Velocity** | 0.10 | Identifies profit inflection points. |
| **F-Score** | 0.10 | Full 9-Pt Piotroski business health. |
| **Leverage** | 0.10 | Debt/Equity penalties (Sect-weighted). |
| **Momentum** | 0.15 | Relative Strength and 52W High proximity. |

---

## 📊 High-Fidelity Backtesting (`backtest_qarp.py`)

The backtest engine simulates real-world trading friction to ensure the Alpha is reproducible.

```bash
python sovereign-cli.py backtest qarp --years 3 --universe 100
```
- **Tiered Slippage**: 0.2% (Large Cap) to 2.0% (Microcap) based on liquidity tiers.
- **Fixed Friction**: 0.2% per round-trip (brokerage + taxes).
- **Survivorship Bias**: Automatically includes `delisted_candidates.txt` in the test universe.
- **Full F-Score**: Utilizes the complete 9-point fundamental health audit.

---

## 🛠️ Unified Operational CLI (`sovereign-cli.py`)

The root directory has been consolidated. All specialized scripts are now accessible through a unified command structure:

### 🗄️ Database (`db`)
- `db init`: Initialize/migrate schemas.
- `db stats`: Instant table audit and row counts.
- `db cleanup`: Vacuum and optimize all SQLite databases.

### 🔍 Universe Scanning (`scan`)
- `scan quick`: Main high-conviction screener run.
- `scan swamp`: Trigger MiroFish Multi-Agent simulation (Offline Fallback enabled).
- `scan master`: Audit the core "Master Picks" list.

### 🔬 Research & ML (`research` / `ml`)
- `ml train`: Retrain the XGBoost Meta-Model on PIT data.
- `ml explain --symbol TICKER`: Generate SHAP values for a specific stock's score.
- `research alpha`: Calculate historical alpha attribution.

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
