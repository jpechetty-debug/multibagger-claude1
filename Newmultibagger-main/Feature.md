# Sovereign Terminal: Feature Roadmap

## Phase 1: Institutional Foundation (V3.0 - Completed)
- **Nexus Alpha v11.0**: 9-factor institutional scoring engine with Sigmoid normalization.
- **Multibagger Compounding Lens**: Multi-period CAGR tracking and consistency auditing.
- **Technical Brutalist UI**: High-density React interface with real-time WebSocket updates.
- **Global API Security**: X-API-Key heart-beat protection for all data routes.
- **Consolidated Entry Point**: `sovereign_cli.py` for all operational and research tasks.

## Phase 2: Intelligence & Deep Research (Completed)
- **[DONE] Quarterly Results Timeline**: Historical trend analysis for revenue, margins, and profit consistency.
- **[DONE] ML Hybrid Scorer**: XGBoost + SHAP explainable investment convictions with walk-forward validation.
- **[DONE] Sector Pulse**: Sector-relative filtering with outperformance ratio benchmarks.
- **[DONE] Liquidity Simulator**: Impact cost estimation and slippage modelling for micro-cap entries.

## Phase 3: Analytical Engine & Multi-Tier Screening (Completed)
- **[DONE] Sector-Relative Filter (3.1)**: `build_sector_relative_filter` — ROE/Growth/PE vs sector medians.
- **[DONE] Earnings Velocity Evaluator (3.2)**: `_margin_expansion_slope` — linear regression of net margins across quarters.
- **[DONE] Friction-Aware Liquidity Gate (3.3)**: `liquidity_gate` — pre-trade slippage rejection for illiquid stocks.
- **[DONE] Tiered Multibagger Classification**: 4-tier system (Compounder, Turnaround, Disruptor, Deep Value) integrated into screener.
- **[DONE] Pipeline Integration**: All Phase 3 modules wired into `screener.py` — every scanned stock now carries tier, slippage, and earnings velocity fields.

## Phase 4: Automation & Scaling (Upcoming)
- **Nexus Quant Allocation**: Automated portfolio construction based on signal conviction.
- **Autonomous Watchdog**: Background worker for real-time audit alerts on portfolio holdings.
- **Multi-Cloud Deployment**: Production-ready Kubernetes/Helm orchestration for distributed scanning.
- **Advanced Backtesting**: Walk-forward optimization and regime-switching performance metrics.

---
*Note: Technical implementation details for specific features are moved to internal documentation or ARCHITECTURE.md.*