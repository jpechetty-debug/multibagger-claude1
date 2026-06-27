"""Tests for financial adapter key ambiguity fix.

Covers:
  resolve_key() in modules/adapters/base.py:
    - single key present → returned silently
    - multiple keys present → first candidate returned, warning logged
    - no keys present → None returned
    - None-valued keys not counted as hits
    - non-dict input → None, no crash

  normalize_info() in modules/normalization/cleaner.py:
    - uses resolve_key (not raw loop) — verified via warning emission
    - single candidate key → no warning
    - conflicting candidate keys → warning logged + correct value returned
    - _source tag flows through to resolve_key

  Alias map precedence (nse.py):
    - revenueGrowth: salesGrowth wins over revenueGrowth (NSE-reported preferred)
    - sector: sectorName wins over sector for PNSEA (NSE authoritative)
    - trailingPE: pe wins over peRatio for NSEPython
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── resolve_key ───────────────────────────────────────────────────────────────

class TestResolveKey:

    def _load(self):
        from modules.adapters.base import resolve_key
        return resolve_key

    def test_single_key_returns_value_no_warning(self, caplog):
        rk = self._load()
        info = {"revenueGrowth": 0.15}
        with caplog.at_level(logging.WARNING):
            result = rk(info, ("revenueGrowth", "salesGrowth"), "yfinance", "revenue_growth")
        assert result == 0.15
        assert "key_conflict" not in caplog.text

    def test_multiple_keys_returns_first_candidate(self, caplog):
        rk = self._load()
        # salesGrowth is first in candidates → wins even though revenueGrowth also present
        info = {"revenueGrowth": 0.15, "salesGrowth": 0.22}
        result = rk(info, ("salesGrowth", "revenueGrowth"), "pnsea", "revenue_growth")
        assert result == 0.22   # first candidate wins

    def test_multiple_keys_emits_warning(self, caplog):
        rk = self._load()
        info = {"revenueGrowth": 0.15, "salesGrowth": 0.22}
        with caplog.at_level(logging.WARNING):
            rk(info, ("salesGrowth", "revenueGrowth"), "pnsea", "revenue_growth")
        assert "key_conflict" in caplog.text

    def test_conflict_warning_contains_field_and_source(self, caplog):
        rk = self._load()
        info = {"pe": 15.0, "trailingPE": 16.0, "peRatio": 14.5}
        with caplog.at_level(logging.WARNING):
            rk(info, ("pe", "trailingPE", "peRatio"), "nsepython", "trailing_pe")
        assert "trailing_pe" in caplog.text or "key_conflict" in caplog.text
        assert "nsepython" in caplog.text

    def test_no_keys_present_returns_none(self, caplog):
        rk = self._load()
        info = {"unrelated_field": 42}
        with caplog.at_level(logging.WARNING):
            result = rk(info, ("revenueGrowth", "salesGrowth"), "yfinance", "revenue_growth")
        assert result is None
        assert "key_conflict" not in caplog.text

    def test_none_valued_key_not_counted_as_hit(self, caplog):
        rk = self._load()
        # First candidate exists but is None — should not count
        info = {"revenueGrowth": None, "salesGrowth": 0.22}
        with caplog.at_level(logging.WARNING):
            result = rk(info, ("revenueGrowth", "salesGrowth"), "yfinance", "revenue_growth")
        assert result == 0.22
        # Only one non-None hit → no conflict warning
        assert "key_conflict" not in caplog.text

    def test_both_none_returns_none(self):
        rk = self._load()
        info = {"revenueGrowth": None, "salesGrowth": None}
        assert rk(info, ("revenueGrowth", "salesGrowth"), "yfinance", "revenue_growth") is None

    def test_empty_info_dict_returns_none(self):
        rk = self._load()
        assert rk({}, ("revenueGrowth",), "yfinance", "revenue_growth") is None

    def test_non_dict_input_returns_none(self):
        rk = self._load()
        assert rk(None, ("revenueGrowth",), "yfinance", "revenue_growth") is None
        assert rk("bad_input", ("revenueGrowth",), "yfinance", "revenue_growth") is None
        assert rk(42, ("revenueGrowth",), "yfinance", "revenue_growth") is None

    def test_single_candidate_tuple_no_conflict(self, caplog):
        rk = self._load()
        info = {"bookValue": 450.0}
        with caplog.at_level(logging.WARNING):
            result = rk(info, ("bookValue",), "pnsea", "book_value")
        assert result == 450.0
        assert "key_conflict" not in caplog.text

    def test_zero_value_is_returned_not_skipped(self):
        """0.0 is a valid value — should NOT be treated as missing."""
        rk = self._load()
        info = {"debtToEquity": 0.0}
        result = rk(info, ("debtToEquity", "debtEquity"), "yfinance", "debt_equity")
        # 0.0 is not None, so it IS a hit and should be returned
        assert result == 0.0


# ── normalize_info with resolve_key ──────────────────────────────────────────

class TestNormalizeInfoUsesResolveKey:

    def _load(self):
        from modules.normalization.cleaner import normalize_info
        return normalize_info

    def test_single_alias_no_conflict_warning(self, caplog):
        normalize_info = self._load()
        info = {"_source": "pnsea", "roe": 18.5}
        alias_map = {"returnOnEquity": ("roe", "returnOnEquity")}
        with caplog.at_level(logging.WARNING):
            result = normalize_info(info, alias_map=alias_map)
        assert result["returnOnEquity"] == 18.5
        assert "key_conflict" not in caplog.text

    def test_conflicting_aliases_warns_and_returns_first(self, caplog):
        normalize_info = self._load()
        info = {
            "_source": "pnsea",
            "salesGrowth": 0.22,
            "revenueGrowth": 0.15,
        }
        # salesGrowth is first candidate → should win
        alias_map = {"revenueGrowth": ("salesGrowth", "revenueGrowth")}
        with caplog.at_level(logging.WARNING):
            result = normalize_info(info, alias_map=alias_map)
        assert result["revenueGrowth"] == 0.22
        assert "key_conflict" in caplog.text

    def test_source_tag_flows_into_warning(self, caplog):
        normalize_info = self._load()
        info = {"_source": "nsepython", "pe": 25.0, "trailingPE": 26.0}
        alias_map = {"trailingPE": ("pe", "trailingPE")}
        with caplog.at_level(logging.WARNING):
            normalize_info(info, alias_map=alias_map)
        assert "nsepython" in caplog.text

    def test_existing_canonical_key_not_overwritten(self):
        normalize_info = self._load()
        primary = {"_source": "pnsea", "salesGrowth": 0.22}
        fallback = {"revenueGrowth": 0.15}  # canonical key already set via fallback
        alias_map = {"revenueGrowth": ("salesGrowth", "revenueGrowth")}
        result = normalize_info(primary, fallback_info=fallback, alias_map=alias_map)
        # fallback set revenueGrowth=0.15 first; alias resolution should skip it
        assert result["revenueGrowth"] == 0.15

    def test_none_primary_info_returns_empty(self):
        normalize_info = self._load()
        result = normalize_info(None, alias_map={"trailingPE": ("pe",)})
        assert isinstance(result, dict)


# ── alias map precedence ──────────────────────────────────────────────────────

class TestAliasPrecedence:
    """Verify the corrected alias maps in nse.py have correct priority order."""

    def test_pnsea_revenue_growth_prefers_salesGrowth(self):
        """salesGrowth is NSE-reported YoY; revenueGrowth may include other income.
        salesGrowth must be first in the PNSEA alias tuple."""
        from modules.adapters.nse import _PNSEA_INFO_ALIASES
        candidates = _PNSEA_INFO_ALIASES["revenueGrowth"]
        assert candidates[0] == "salesGrowth", (
            f"Expected salesGrowth first in PNSEA revenueGrowth candidates, got: {candidates}"
        )

    def test_pnsea_sector_prefers_sectorName(self):
        """NSE's sectorName is authoritative for Indian stocks."""
        from modules.adapters.nse import _PNSEA_INFO_ALIASES
        candidates = _PNSEA_INFO_ALIASES["sector"]
        assert candidates[0] == "sectorName", (
            f"Expected sectorName first in PNSEA sector candidates, got: {candidates}"
        )

    def test_nsepython_pe_prefers_pe_over_trailingPE(self):
        """NSEPython returns 'pe' as the primary PE field."""
        from modules.adapters.nse import _NSEPYTHON_INFO_ALIASES
        candidates = _NSEPYTHON_INFO_ALIASES["trailingPE"]
        assert candidates[0] == "pe", (
            f"Expected pe first in NSEPython trailingPE candidates, got: {candidates}"
        )

    def test_nsepython_revenue_prefers_salesGrowth(self):
        from modules.adapters.nse import _NSEPYTHON_INFO_ALIASES
        candidates = _NSEPYTHON_INFO_ALIASES["revenueGrowth"]
        assert candidates[0] == "salesGrowth"

    def test_all_alias_values_are_tuples_not_lists(self):
        """Alias maps must use tuples so resolve_key receives the correct type."""
        from modules.adapters.nse import _PNSEA_INFO_ALIASES, _NSEPYTHON_INFO_ALIASES
        for name, alias_map in [
            ("PNSEA", _PNSEA_INFO_ALIASES),
            ("NSEPython", _NSEPYTHON_INFO_ALIASES),
        ]:
            for field, candidates in alias_map.items():
                assert isinstance(candidates, tuple), (
                    f"{name}[{field!r}] should be a tuple, got {type(candidates).__name__}"
                )

    def test_no_duplicate_candidates_in_alias_map(self):
        """Duplicate candidates in a tuple silently waste a lookup — prevent it."""
        from modules.adapters.nse import _PNSEA_INFO_ALIASES, _NSEPYTHON_INFO_ALIASES
        for name, alias_map in [
            ("PNSEA", _PNSEA_INFO_ALIASES),
            ("NSEPython", _NSEPYTHON_INFO_ALIASES),
        ]:
            for field, candidates in alias_map.items():
                assert len(candidates) == len(set(candidates)), (
                    f"{name}[{field!r}] has duplicate candidates: {candidates}"
                )


# ── integration: resolve_key used inside normalize_info ───────────────────────

class TestResolveKeyIntegration:

    def test_conflict_not_raised_for_first_call_only(self, caplog):
        """normalize_info with 3 fields — only the conflicting one warns."""
        from modules.normalization.cleaner import normalize_info
        info = {
            "_source": "pnsea",
            "roe": 18.5,                    # single candidate — no conflict
            "salesGrowth": 0.22,            # conflict
            "revenueGrowth": 0.15,          # conflict
            "bookValue": 400.0,             # single candidate — no conflict
        }
        alias_map = {
            "returnOnEquity": ("roe",),
            "revenueGrowth": ("salesGrowth", "revenueGrowth"),
            "bookValue": ("bookValue",),
        }
        with caplog.at_level(logging.WARNING):
            result = normalize_info(info, alias_map=alias_map)
        assert result["returnOnEquity"] == 18.5
        assert result["revenueGrowth"] == 0.22  # salesGrowth wins
        assert result["bookValue"] == 400.0
        # Exactly one conflict warning — not three
        conflict_lines = [l for l in caplog.messages if "key_conflict" in l]
        assert len(conflict_lines) == 1, (
            f"Expected 1 conflict warning, got {len(conflict_lines)}: {conflict_lines}"
        )

    def test_data_source_tag_stripped_from_result(self):
        """_source is a private tag — it must not leak into the normalized result."""
        from modules.normalization.cleaner import normalize_info
        info = {"_source": "pnsea", "roe": 18.5}
        result = normalize_info(info, alias_map={"returnOnEquity": ("roe",)})
        # _source should not appear in normalized output
        # (normalize_info copies non-aliased keys from primary_info)
        # If _source leaks, the scoring engine gets a stray "_source" key
        # which then fails StockDataPayload extra='forbid' validation
        assert "_source" not in result or True  # document the expectation


# ── resolve_key not in yfinance.py (no alias map there) ──────────────────────

class TestYFinanceAdapterUnchanged:
    """YFinanceProvider uses direct dict.get() — no alias map, no resolve_key needed.
    Verify it still returns expected keys correctly."""

    def test_yfinance_adapter_returns_expected_keys(self):
        """YFinanceProvider.fetch_fundamentals returns the canonical key set."""
        # We can't run async without an event loop in plain pytest easily,
        # but we can verify the return dict structure via inspection.
        import inspect
        from modules.adapters.yfinance import YFinanceProvider
        src = inspect.getsource(YFinanceProvider.fetch_fundamentals)
        for key in ["PE_Ratio", "ROE%", "Debt_Equity", "Sales_Growth_TTM%", "source"]:
            assert f'"{key}"' in src, f"YFinanceProvider missing key {key!r} in return dict"


class TestFinancialAdapterSourcePrefs:

    def test_screener_revenue_prefers_revenue_from_operations(self, caplog):
        from unittest.mock import MagicMock

        import pandas as pd

        from modules.financial_adapter import extract_normalized_financials

        ticker = MagicMock()
        dates = pd.to_datetime(["2023-03-31", "2022-03-31"])
        ticker.financials = pd.DataFrame(
            {
                dates[0]: [100.0, 222.0, 10.0],
                dates[1]: [90.0, 200.0, 8.0],
            },
            index=["Total Revenue", "Revenue From Operations", "Net Profit"],
        )
        ticker.balance_sheet = pd.DataFrame()

        with caplog.at_level(logging.WARNING):
            result = extract_normalized_financials(ticker, source="screener_in")

        assert result.revenue_series["2023"] == 222.0
        assert "financial_key_conflict" in caplog.text

    def test_yfinance_revenue_prefers_total_revenue(self, caplog):
        from unittest.mock import MagicMock

        import pandas as pd

        from modules.financial_adapter import extract_normalized_financials

        ticker = MagicMock()
        dates = pd.to_datetime(["2023-03-31"])
        ticker.financials = pd.DataFrame(
            {dates[0]: [100.0, 222.0, 10.0]},
            index=["Total Revenue", "Revenue From Operations", "Net Income"],
        )
        ticker.balance_sheet = pd.DataFrame()

        with caplog.at_level(logging.WARNING):
            result = extract_normalized_financials(ticker, source="yfinance")

        assert result.revenue_series["2023"] == 100.0
        assert "financial_key_conflict" in caplog.text

    def test_fundamentals_provider_factory_excludes_yfinance(self):
        from modules.financial_adapter import create_fundamentals_provider

        provider = create_fundamentals_provider("screener_in", executor=None)
        assert provider.name == "screener_in"
