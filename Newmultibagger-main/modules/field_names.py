"""
Sovereign Terminal — Field Mapping Source of Truth
Bidirectional field mappings between Python/Scoring/Screener keys (capitalized/camelCase/with symbols)
and database column names (snake_case).

Also exposes ``normalize_data_keys(data)`` which promotes any snake_case or
legacy alias keys in a raw dict to the canonical Title-case keys used by the
scoring engine.  Call this once at the scoring boundary so every downstream
module can assume canonical keys and avoid dual-key ``or`` lookups.
"""

from __future__ import annotations

FIELD_MAPPING: dict[str, str] = {
    "Symbol": "symbol",
    "Price": "price",
    "Sector": "sector",
    "Score": "score",
    "F_Score": "f_score",
    "Rating": "rating",
    "Buy_Below": "buy_below",
    "Stop_Loss": "stop_loss",
    "Target_1": "target_1",
    "Target_2": "target_2",
    "Sales_Growth_TTM%": "sales_growth",
    "ROE%": "roe",
    "PEG_Ratio": "peg_ratio",
    "Debt_Equity": "debt_equity",
    "RSI": "rsi",
    "Smart_Money%": "smart_money",
    "Market_Cap_Cr": "market_cap_cr",
    "CFO_PAT_Ratio": "cfo_pat_ratio",
    "Sales_Growth_5Y%": "sales_cagr_5y",
    "Avg_ROE_5Y%": "avg_roe_5y",
    "PE_Ratio": "pe_ratio",
    "Down_From_52W_High%": "down_from_52w",
    "RS_Rating": "rs_rating",
    "Earnings_Accel": "earnings_accel",
    "Sector_Leader": "sector_leader",
    "Graham_Number": "graham_number",
    "Value_Gap%": "value_gap",
    "Technical_Signal": "technical_signal",
    "Analyst_Rating": "analyst_rating",
    "Analyst_Upside%": "analyst_upside",
    "Promoter_Holding%": "promoter_holding",
    "Inst_Holding%": "inst_holding",
    "ATR": "atr",
    "Stop_Loss_ATR": "stop_loss_atr",
    "Max_Qty_1L": "max_qty_1l",
    "As_Of_Date": "as_of_date",
    "updated_at": "updated_at",
    "Conviction_Score": "conviction_score",
    "Conviction_Boost": "conviction_boost",
    "Institutional_Interest": "institutional_interest",
    "Super_Investors": "super_investors",
    "Data_Quality": "data_quality",
    "Data_Confidence": "data_confidence",
    "F_Score_Method": "f_score_method",
    "Backtest_CAGR": "backtest_cagr",
    "Backtest_Win_Rate": "backtest_win_rate",
    "Backtest_Max_DD": "backtest_max_dd",
    "Backtest_Sharpe": "backtest_sharpe",
    "ML_Predicted_Return": "ml_predicted_return",
    "SHAP_Breakdown": "shap_breakdown",
    "High_52W": "high_52w",
    "Low_52W": "low_52w",
    "Pledge_Pct": "pledge_pct",
    "Piotroski_Score": "piotroski_score",
    "ROCE_pct": "roce",
    "Median_PAT_Growth_5Y_pct": "median_pat_growth",
    "ml_rank_score": "ml_rank_score",
    "Ret_1M": "ret_1m",
    "Ret_3M": "ret_3m",
    "Ret_6M": "ret_6m",
    "Vol_Breakout": "vol_breakout",
    "Dist_From_52W_High": "dist_from_52w_high",
    "Revenue_CAGR_3Y": "revenue_cagr_3y",
    "Revenue_CAGR_5Y": "revenue_cagr_5y",
    "PAT_CAGR_3Y": "pat_cagr_3y",
    "PAT_CAGR_5Y": "pat_cagr_5y",
    "EPS_CAGR_3Y": "eps_cagr_3y",
    "EPS_CAGR_5Y": "eps_cagr_5y",
    "CAGR_Consistency": "cagr_consistency",
    "Dividend_Yield": "dividend_yield",
    "Dividend_Payout": "dividend_payout",
    "Cap_Category": "cap_category",
    "Data_Quality_Flags": "data_quality_flags",
    # Scoring engine fields not previously in the map
    "EPS_Growth%": "eps_growth",
    "Down_From_52W_High%": "down_from_52w_high",  # alias kept for scorer; DB col is down_from_52w
    "Profit_Margin%": "profit_margin",
    "Quarter_End": "quarter_end",
    "Earnings_Inflection_Score": "earnings_inflection_score",
    "Estimate_Score_Adj": "estimate_score_adj",
    "Backtest": "backtest",
}

# Reverse mapping: snake_case DB column → canonical Title-case scoring key.
# Built automatically from FIELD_MAPPING so there is one source of truth.
REVERSE_FIELD_MAPPING: dict[str, str] = {v: k for k, v in FIELD_MAPPING.items()}

# Extra snake_case aliases that appear in DB reads but whose canonical name
# differs from what REVERSE_FIELD_MAPPING produces (e.g. the DB column is
# ``down_from_52w`` but the scorer expects ``Down_From_52W_High%``).
_EXTRA_ALIASES: dict[str, str] = {
    "down_from_52w": "Down_From_52W_High%",
    "down_from_52w_high": "Down_From_52W_High%",
    "sales_growth": "Sales_Growth_TTM%",  # DB ``sales_growth`` maps to TTM variant
    "eps_growth": "EPS_Growth%",
    "roe": "ROE%",
    "avg_roe_5y": "Avg_ROE_5Y%",
    "sales_cagr_5y": "Sales_Growth_5Y%",
    "pledge_pct": "Pledge_Pct",
    "profit_margin": "Profit_Margin%",
}

# Combined lookup used by normalize_data_keys: snake_case → canonical Title-case.
# _EXTRA_ALIASES wins over REVERSE_FIELD_MAPPING on conflicts (more specific).
_SNAKE_TO_CANONICAL: dict[str, str] = {**REVERSE_FIELD_MAPPING, **_EXTRA_ALIASES}


def normalize_data_keys(data: dict) -> dict:
    """Return a copy of *data* with all snake_case / alias keys promoted to
    their canonical Title-case equivalents used by the scoring engine.

    Keys that are already canonical (or unknown) are preserved unchanged.
    This is a pure function — it never mutates the input dict.

    Example::

        normalize_data_keys({"avg_roe_5y": 22.5, "Symbol": "TCS.NS"})
        # → {"Avg_ROE_5Y%": 22.5, "Symbol": "TCS.NS"}
    """
    out: dict = {}
    for key, value in data.items():
        canonical = _SNAKE_TO_CANONICAL.get(key)
        if canonical is not None and canonical not in data:
            # Promote to canonical key only when the canonical key is not
            # already present (caller's explicit value always takes priority).
            out[canonical] = value
        else:
            out[key] = value
    return out
