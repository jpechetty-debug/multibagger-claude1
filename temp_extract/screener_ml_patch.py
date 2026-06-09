# scripts/internal/screener.py — PHASE 88 PATCH
#
# Problem
# -------
# The existing Phase 88 block (around line 1890) only passes 7 of the 13
# FEATURES to predict_and_explain:
#
#   factors = {
#       "score":          score,
#       "sales_cagr_5y":  stock.get("Sales_Growth_5Y%", 0),
#       "avg_roe_5y":     stock.get("Avg_ROE_5Y%", 0),
#       "pe_ratio":       stock.get("PE_Ratio", 0),
#       "debt_equity":    stock.get("Debt_Equity", 0),
#       "cfo_pat_ratio":  stock.get("CFO_PAT_Ratio", 0),
#       "market_cap_cr":  stock.get("Market_Cap_Cr", 0),
#   }
#
# The 6 missing features are: ret_1m, ret_3m, ret_6m, vol_breakout,
# dist_from_52w_high, roce — all of which are available in the stock
# dict at this point in the pipeline.
#
# _alias_factors() zero-fills missing keys, so the model runs silently
# but with 6 dead features. The IC drops materially because momentum and
# ROCE are strong predictors in the NSE universe.
#
# Fix
# ---
# In scripts/internal/screener.py, find the Phase 88 block and replace
# the entire try/except with the block below.
#
# HOW TO APPLY
# ────────────
# Find this exact line in screener.py:
#
#   # --- Phase 88: Hybrid Scoring (ML) ---
#
# Replace everything from that comment down to and including:
#
#   except Exception:
#       # Silent fail if ML model not ready
#       stock["ML_Predicted_Return"] = None
#       stock["SHAP_Breakdown"] = "{}"
#
# With the block below.

            # --- Phase 88: Hybrid Scoring (ML) ---
            try:
                from modules.hybrid_scoring import predict_and_explain

                factors = {
                    # ── Fundamental features ─────────────────────────────
                    "score":               score,
                    "sales_cagr_5y":       stock.get("Sales_Growth_5Y%",   0) or 0,
                    "avg_roe_5y":          stock.get("Avg_ROE_5Y%",        0) or 0,
                    "pe_ratio":            stock.get("PE_Ratio",            0) or 0,
                    "debt_equity":         stock.get("Debt_Equity",         0) or 0,
                    "cfo_pat_ratio":       stock.get("CFO_PAT_Ratio",       0) or 0,
                    "market_cap_cr":       stock.get("Market_Cap_Cr",       0) or 0,
                    "roce":                stock.get("ROCE%",               0) or 0,
                    # ── Momentum / technical features ────────────────────
                    "ret_1m":              stock.get("Ret_1M",              0) or 0,
                    "ret_3m":              stock.get("Ret_3M",              0) or 0,
                    "ret_6m":              stock.get("Ret_6M",              0) or 0,
                    "vol_breakout":        stock.get("Vol_Breakout",        0) or 0,
                    "dist_from_52w_high":  stock.get("Dist_From_52W_High",  0) or 0,
                }

                ml_res = predict_and_explain(factors)
                stock["ML_Predicted_Return"] = ml_res.get("ml_prediction")
                stock["SHAP_Breakdown"]      = json.dumps(ml_res.get("shap_values", {}))
                stock["SHAP_Top_Drivers"]    = json.dumps(ml_res.get("top_drivers",  []))

            except Exception:
                # Silent fail — model may not be trained yet
                stock["ML_Predicted_Return"] = None
                stock["SHAP_Breakdown"]      = "{}"
                stock["SHAP_Top_Drivers"]    = "[]"
