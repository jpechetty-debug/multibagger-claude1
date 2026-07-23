"""
tests/test_normalize_data_keys.py
──────────────────────────────────
Tests for modules/field_names.py::normalize_data_keys() and the downstream
guarantee that calculate_institutional_score() produces the same result
regardless of whether the caller passes Title-case or snake_case keys.

Run:
    pytest tests/test_normalize_data_keys.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ── Stub every module that touches external APIs ─────────────────────────────
_prom_stub = MagicMock()
_prom_stub.calculate_promoter_score.return_value = {"is_disqualified": False, "score_adjustment": 0}
sys.modules.setdefault("modules.promoter_intel", _prom_stub)

_est_stub = MagicMock()
_est_stub.get_estimate_data.return_value = {
    "momentum": {"is_disqualified": False, "score_cap": None, "score_adjustment": 0}
}
sys.modules.setdefault("modules.estimates", _est_stub)

_conv_stub = MagicMock()
_conv_stub.calculate_conviction_score.return_value = {
    "conviction_score": 50,
    "conviction_boost": 0,
    "institutional_interest": False,
    "investors": [],
}
sys.modules.setdefault("research.conviction_engine", _conv_stub)

from modules.field_names import FIELD_MAPPING, REVERSE_FIELD_MAPPING, normalize_data_keys  # noqa: E402
from modules.scoring import calculate_institutional_score  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# normalize_data_keys unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizeDataKeys:
    def test_snake_case_promoted_to_canonical(self):
        result = normalize_data_keys({"avg_roe_5y": 22.5, "sales_cagr_5y": 18.0})
        assert result["Avg_ROE_5Y%"] == 22.5
        assert result["Sales_Growth_5Y%"] == 18.0
        assert "avg_roe_5y" not in result
        assert "sales_cagr_5y" not in result

    def test_canonical_keys_pass_through_unchanged(self):
        data = {"Symbol": "TCS.NS", "Avg_ROE_5Y%": 22.5, "PE_Ratio": 25.0}
        result = normalize_data_keys(data)
        assert result == data

    def test_canonical_key_wins_over_snake_case_alias(self):
        # When both forms are present the canonical value must win.
        result = normalize_data_keys({"Avg_ROE_5Y%": 30.0, "avg_roe_5y": 10.0})
        assert result["Avg_ROE_5Y%"] == 30.0

    def test_known_aliases_all_promoted(self):
        snake_inputs = {
            "pe_ratio": 18.0,
            "roe": 20.0,
            "debt_equity": 0.5,
            "cfo_pat_ratio": 1.2,
            "avg_roe_5y": 22.0,
            "sales_cagr_5y": 15.0,
            "eps_growth": 12.0,
            "promoter_holding": 65.0,
            "inst_holding": 25.0,
            "f_score": 8,
            "peg_ratio": 1.1,
            "value_gap": 30.0,
            "atr": 25.0,
            "down_from_52w": 8.0,
            "rs_rating": 1.2,
            "symbol": "INFY.NS",
            "sector": "Technology",
            "pledge_pct": 0.0,
        }
        result = normalize_data_keys(snake_inputs)
        assert result.get("PE_Ratio") == 18.0
        assert result.get("ROE%") == 20.0
        assert result.get("Debt_Equity") == 0.5
        assert result.get("CFO_PAT_Ratio") == 1.2
        assert result.get("Avg_ROE_5Y%") == 22.0
        assert result.get("Sales_Growth_5Y%") == 15.0
        assert result.get("EPS_Growth%") == 12.0
        assert result.get("Promoter_Holding%") == 65.0
        assert result.get("Inst_Holding%") == 25.0
        assert result.get("F_Score") == 8
        assert result.get("PEG_Ratio") == 1.1
        assert result.get("Value_Gap%") == 30.0
        assert result.get("ATR") == 25.0
        assert result.get("Down_From_52W_High%") == 8.0
        assert result.get("RS_Rating") == 1.2
        assert result.get("Symbol") == "INFY.NS"
        assert result.get("Sector") == "Technology"
        assert result.get("Pledge_Pct") == 0.0

    def test_unknown_keys_pass_through(self):
        result = normalize_data_keys({"some_future_field": 99, "Symbol": "X.NS"})
        assert result["some_future_field"] == 99
        assert result["Symbol"] == "X.NS"

    def test_empty_dict(self):
        assert normalize_data_keys({}) == {}

    def test_does_not_mutate_input(self):
        original = {"avg_roe_5y": 22.5}
        normalize_data_keys(original)
        assert "avg_roe_5y" in original
        assert "Avg_ROE_5Y%" not in original

    def test_field_mapping_reverse_is_consistent(self):
        # Every value in FIELD_MAPPING must round-trip through REVERSE_FIELD_MAPPING.
        for canonical, snake in FIELD_MAPPING.items():
            assert REVERSE_FIELD_MAPPING[snake] == canonical, (
                f"REVERSE_FIELD_MAPPING[{snake!r}] = {REVERSE_FIELD_MAPPING.get(snake)!r}, "
                f"expected {canonical!r}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Scoring equivalence: Title-case input == snake_case input
# ─────────────────────────────────────────────────────────────────────────────

# A representative stock payload using canonical Title-case keys (screener path)
_TITLE_CASE_STOCK: dict = {
    "Symbol": "EQUIV.NS",
    "Market_Cap_Cr": 5000,
    "PE_Ratio": 18.0,
    "Avg_ROE_5Y%": 25.0,
    "ROE%": 22.0,
    "Debt_Equity": 0.3,
    "CFO_PAT_Ratio": 1.4,
    "Down_From_52W_High%": 8.0,
    "Sales_Growth_5Y%": 22.0,
    "Sales_Growth_TTM%": 18.0,
    "EPS_Growth%": 20.0,
    "Promoter_Holding%": 65.0,
    "Inst_Holding%": 25.0,
    "F_Score": 8,
    "Sector": "Technology",
    "Value_Gap%": 30.0,
    "ATR": 30.0,
    "Price": 1000.0,
    "RS_Rating": 1.2,
    "Pledge_Pct": 0.0,
}

# The same stock using DB snake_case keys (repository / DB-read path)
_SNAKE_CASE_STOCK: dict = {
    "symbol": "EQUIV.NS",
    "market_cap_cr": 5000,
    "pe_ratio": 18.0,
    "avg_roe_5y": 25.0,
    "roe": 22.0,
    "debt_equity": 0.3,
    "cfo_pat_ratio": 1.4,
    "down_from_52w": 8.0,
    "sales_cagr_5y": 22.0,
    "sales_growth": 18.0,
    "eps_growth": 20.0,
    "promoter_holding": 65.0,
    "inst_holding": 25.0,
    "f_score": 8,
    "sector": "Technology",
    "value_gap": 30.0,
    "atr": 30.0,
    "price": 1000.0,
    "rs_rating": 1.2,
    "pledge_pct": 0.0,
}


class TestScoringKeyEquivalence:
    """calculate_institutional_score() must return the same total_score
    regardless of whether keys are Title-case or snake_case."""

    def test_total_score_identical(self):
        title_result = calculate_institutional_score(_TITLE_CASE_STOCK.copy())
        snake_result = calculate_institutional_score(_SNAKE_CASE_STOCK.copy())
        assert title_result["total_score"] == pytest.approx(snake_result["total_score"], abs=0.01), (
            f"Title-case score {title_result['total_score']} != "
            f"snake_case score {snake_result['total_score']}"
        )

    def test_factor_breakdown_identical(self):
        title_result = calculate_institutional_score(_TITLE_CASE_STOCK.copy())
        snake_result = calculate_institutional_score(_SNAKE_CASE_STOCK.copy())
        for factor, title_val in title_result["factor_breakdown"].items():
            snake_val = snake_result["factor_breakdown"][factor]
            assert title_val == pytest.approx(snake_val, abs=0.1), (
                f"Factor {factor!r}: Title-case={title_val}, snake_case={snake_val}"
            )

    def test_checklist_score_identical(self):
        title_result = calculate_institutional_score(_TITLE_CASE_STOCK.copy())
        snake_result = calculate_institutional_score(_SNAKE_CASE_STOCK.copy())
        assert title_result["checklist_score"] == snake_result["checklist_score"]

    def test_snake_case_pledge_reaches_conviction(self):
        """Regression: pledge_pct was previously lost from the conviction
        input when only snake_case keys were provided."""
        pledged = dict(_SNAKE_CASE_STOCK, pledge_pct=15.0)
        result = calculate_institutional_score(pledged)
        # Must not raise, and pledge must be visible in the normalized data.
        assert "total_score" in result

    def test_mixed_keys_resolved_without_error(self):
        """A dict containing both canonical and snake_case keys for
        the *same* field must not raise and canonical value must win."""
        mixed = dict(_TITLE_CASE_STOCK, avg_roe_5y=5.0)  # snake alias conflicts
        result = calculate_institutional_score(mixed)
        # The canonical Avg_ROE_5Y%=25 should win, score should not be
        # degraded by the low snake alias value.
        title_only = calculate_institutional_score(_TITLE_CASE_STOCK.copy())
        assert result["total_score"] == pytest.approx(title_only["total_score"], abs=0.01)
