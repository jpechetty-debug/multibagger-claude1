from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from modules.fundamentals import calculate_dupont_decomposition
from modules.scoring.ceiling import CHECKLIST_TOTAL, _dupont_leverage_flag, build_checklist_status
from modules.scoring.factors import _build_factor_state
from modules.field_names import normalize_data_keys


def test_dupont_decomposition_dict_path_reconstructs_roe():
    # Net Margin 10%, Asset Turnover 1.5x, Financial Leverage 2x -> ROE = 30%
    data = {
        "Net_Income": 150.0,
        "Total_Revenue": 1500.0,
        "Total_Assets": 1000.0,
        "Total_Equity": 500.0,
    }
    result = calculate_dupont_decomposition(data)

    assert result["net_margin_pct"] == 10.0
    assert result["asset_turnover"] == 1.5
    assert result["financial_leverage"] == 2.0
    assert result["roa_pct"] == 15.0
    assert result["implied_roe_pct"] == 30.0


def test_dupont_decomposition_accepts_stockholders_equity_alias():
    data = {
        "Net_Income": 100.0,
        "Total_Revenue": 1000.0,
        "Total_Assets": 800.0,
        "Stockholders_Equity": 400.0,
    }
    result = calculate_dupont_decomposition(data)
    assert result["financial_leverage"] == 2.0


def test_dupont_decomposition_missing_inputs_returns_none_not_zero():
    result = calculate_dupont_decomposition({"Net_Income": 100.0})

    assert result["net_margin_pct"] is None
    assert result["asset_turnover"] is None
    assert result["financial_leverage"] is None
    assert result["roa_pct"] is None
    assert result["implied_roe_pct"] is None


def test_dupont_decomposition_zero_denominator_returns_none_not_crash():
    data = {
        "Net_Income": 100.0,
        "Total_Revenue": 0.0,
        "Total_Assets": 500.0,
        "Total_Equity": 0.0,
    }
    result = calculate_dupont_decomposition(data)

    assert result["net_margin_pct"] is None
    assert result["financial_leverage"] is None
    # ROA only needs net_income and total_assets, both present and nonzero
    assert result["roa_pct"] == 20.0


def test_dupont_decomposition_legacy_ticker_path():
    ticker = SimpleNamespace(
        financials=pd.DataFrame({"2024": [150.0]}, index=["Net Income"]),
        balance_sheet=pd.DataFrame(
            {"2024": [1000.0]}, index=["Total Assets"]
        ),
    )
    # Revenue isn't on this minimal financials frame, so margin/turnover/
    # implied_roe stay None, but roa needs total_assets+net_income only.
    result = calculate_dupont_decomposition(ticker)
    assert result["roa_pct"] == 15.0
    assert result["net_margin_pct"] is None


def test_dupont_decomposition_neither_dict_nor_ticker_returns_empty():
    result = calculate_dupont_decomposition(object())
    assert all(v is None for v in result.values())


def test_dupont_leverage_flag_is_not_applicable_when_data_missing():
    # Rollout-gap case: Financial_Leverage/ROA% not backfilled yet anywhere.
    assert _dupont_leverage_flag({}) is None


def test_dupont_leverage_flag_fails_on_high_leverage_and_weak_roa():
    data = {"Financial_Leverage": 4.0, "ROA%": 3.0}
    assert _dupont_leverage_flag(data) is False


def test_dupont_leverage_flag_passes_on_high_leverage_with_healthy_roa():
    # High leverage alone isn't disqualifying if the core business is efficient.
    data = {"Financial_Leverage": 4.0, "ROA%": 8.0}
    assert _dupont_leverage_flag(data) is True


def test_dupont_leverage_flag_passes_on_low_leverage_even_with_weak_roa():
    data = {"Financial_Leverage": 1.5, "ROA%": 2.0}
    assert _dupont_leverage_flag(data) is True


def _checklist_stock(**overrides):
    stock = {
        "Market_Cap_Cr": 301.0,
        "PE_Ratio": 30.0,
        "Avg_ROE_5Y%": 22.0,
        "ROE%": 20.0,
        "Debt_Equity": 0.4,
        "CFO_PAT_Ratio": 1.3,
        "Down_From_52W_High%": 8.0,
        "Sales_Growth_5Y%": 18.0,
        "Sales_Growth_TTM%": 16.0,
        "EPS_Growth%": 12.0,
        "Promoter_Holding%": 55.0,
        "Inst_Holding%": 20.0,
        "F_Score": 7,
        "Sector": "Technology",
        "Value_Gap%": 10.0,
        "Price": 1000.0,
    }
    stock.update(overrides)
    return stock


def test_default_checklist_total_is_twelve():
    assert CHECKLIST_TOTAL == 12


def test_checklist_new_item_does_not_count_without_dupont_data():
    data = _checklist_stock()
    state = _build_factor_state(data, score_sentiment=50.0, scoring_mode="balanced")
    status = build_checklist_status(data, state)

    assert "ROE Not Purely Leverage-Driven" in status["items"]
    assert status["items"]["ROE Not Purely Leverage-Driven"] is None
    assert status["passed"] == 12
    assert status["total"] == 12


def test_checklist_new_item_fails_when_dupont_data_shows_leverage_driven_roe():
    data = _checklist_stock(**{"Financial_Leverage": 4.5, "ROA%": 2.0})
    state = _build_factor_state(data, score_sentiment=50.0, scoring_mode="balanced")
    status = build_checklist_status(data, state)

    assert status["items"]["ROE Not Purely Leverage-Driven"] is False
    assert status["passed"] == 12
    assert status["total"] == 13


def test_normalize_data_keys_promotes_dupont_snake_case_fields():
    raw = {
        "net_margin_pct": 10.0,
        "asset_turnover": 1.5,
        "financial_leverage": 2.0,
        "roa_pct": 15.0,
    }
    canonical = normalize_data_keys(raw)

    assert canonical["Net_Margin%"] == 10.0
    assert canonical["Asset_Turnover"] == 1.5
    assert canonical["Financial_Leverage"] == 2.0
    assert canonical["ROA%"] == 15.0
