---
type: "query"
date: "2026-06-02T05:30:36.032302+00:00"
question: "Complete Phase 2 data pipeline trustworthiness fixes"
contributor: "graphify"
source_nodes: ["FundamentalsProvider", "DataManager", "validate_dataframe", "VectorBTEngine", "calculate_institutional_score"]
---

# Q: Complete Phase 2 data pipeline trustworthiness fixes

## Answer

Implemented Phase 2 fixes in order: financial_adapter now defines FundamentalsProvider and env-switchable non-yFinance fundamentals provider factory; DataManager defaults to Screener/NSE fundamentals and uses yFinance only for price/history fallback; financial_adapter has _SOURCE_KEY_PREFS and conflict warnings; DQ sectors are canonicalized before db limit lookup; root GitHub data freshness workflow validates nse_listing_dates.csv; transaction costs now include brokerage, GST, STT, SEBI, stamp, and 0.1*sqrt(trade_value/ADV) impact; stale fundamentals return a STALE_DATA score result; Phase 2 tests and ruff pass.

## Source Nodes

- FundamentalsProvider
- DataManager
- validate_dataframe
- VectorBTEngine
- calculate_institutional_score