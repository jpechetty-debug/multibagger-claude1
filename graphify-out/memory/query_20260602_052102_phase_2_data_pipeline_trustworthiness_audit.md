---
type: "query"
date: "2026-06-02T05:21:02.923575+00:00"
question: "Phase 2 data pipeline trustworthiness audit"
contributor: "graphify"
source_nodes: ["validate_dataframe", "ScreenerInProvider", "VectorBTEngine", "calculate_institutional_score"]
---

# Q: Phase 2 data pipeline trustworthiness audit

## Answer

Phase 2 is partially complete: DQ limits, survivorship data, Sortino/Calmar, Screener provider, and freshness warnings exist; incomplete items are financial_adapter abstraction/source-key prefs, yFinance still used as fundamentals fallback, nested CI workflow placement, transaction cost missing brokerage/GST and impact coefficient mismatch, and stale hard gate raises instead of returning STALE_DATA result.

## Source Nodes

- validate_dataframe
- ScreenerInProvider
- VectorBTEngine
- calculate_institutional_score