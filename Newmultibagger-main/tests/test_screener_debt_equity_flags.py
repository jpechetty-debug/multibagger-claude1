from scripts.internal import screener


# ── _resolve_debt_equity ─────────────────────────────────────────────────


def test_resolve_debt_equity_prefers_canonical_clean_ratio():
    # Canonical source (Screener.in / NSE XBRL) already reports a clean
    # ratio — must be used as-is, NOT divided by 100.
    raw = {"Debt_Equity": 0.35}
    info = {"debtToEquity": 999}  # should be ignored entirely
    assert screener._resolve_debt_equity(raw, info) == 0.35


def test_resolve_debt_equity_canonical_zero_is_trusted_not_treated_as_missing():
    # A debt-free company: 0.0 is a real value, not "absent" — must not
    # fall through to the yfinance branch.
    raw = {"Debt_Equity": 0.0}
    info = {"debtToEquity": 55.0}
    assert screener._resolve_debt_equity(raw, info) == 0.0


def test_resolve_debt_equity_falls_back_to_yfinance_percentage_scale():
    # No canonical value present -> fall back to yfinance's info dict,
    # which reports NSE/BSE debtToEquity on a 0-100+ scale needing /100.
    raw = {}
    info = {"debtToEquity": 35.0}
    assert screener._resolve_debt_equity(raw, info) == 0.35


def test_resolve_debt_equity_does_not_rescale_small_yfinance_values():
    # Legacy behaviour: yfinance values <= 10 are assumed already a clean
    # ratio (e.g. 0.35) and are left untouched.
    raw = {}
    info = {"debtToEquity": 0.35}
    assert screener._resolve_debt_equity(raw, info) == 0.35


def test_resolve_debt_equity_no_data_defaults_to_zero():
    assert screener._resolve_debt_equity({}, {}) == 0.0


def test_resolve_debt_equity_ignores_non_finite_canonical_value():
    raw = {"Debt_Equity": None}
    info = {"debtToEquity": 40.0}
    assert screener._resolve_debt_equity(raw, info) == 0.4


# ── _resolve_book_value ──────────────────────────────────────────────────


def test_resolve_book_value_prefers_canonical_when_present():
    raw = {"Book_Value": 120.5}
    info = {"bookValue": 80.0}
    assert screener._resolve_book_value(raw, info) == 120.5


def test_resolve_book_value_canonical_zero_treated_as_absent():
    # Unlike Debt_Equity, a book value of exactly 0 is treated as missing
    # (matches the _is_present_metric convention used elsewhere in this
    # module), so it should fall through to yfinance.
    raw = {"Book_Value": 0.0}
    info = {"bookValue": 45.0}
    assert screener._resolve_book_value(raw, info) == 45.0


def test_resolve_book_value_falls_back_to_yfinance():
    raw = {}
    info = {"bookValue": 45.0}
    assert screener._resolve_book_value(raw, info) == 45.0


def test_resolve_book_value_no_data_defaults_to_zero():
    assert screener._resolve_book_value({}, {}) == 0


# ── _merge_data_quality_flags ────────────────────────────────────────────


def test_merge_data_quality_flags_handles_list_from_provider():
    # e.g. NSEXBRLProvider's payload shape
    merged = screener._merge_data_quality_flags("", ["nse_xbrl_as_of_date_estimated"])
    assert merged == "nse_xbrl_as_of_date_estimated"


def test_merge_data_quality_flags_appends_to_existing_string():
    merged = screener._merge_data_quality_flags(
        "mock_history", ["nse_xbrl_as_of_date_estimated"]
    )
    assert merged == "mock_history,nse_xbrl_as_of_date_estimated"


def test_merge_data_quality_flags_dedupes_against_existing():
    merged = screener._merge_data_quality_flags(
        "nse_xbrl_as_of_date_estimated", ["nse_xbrl_as_of_date_estimated"]
    )
    assert merged == "nse_xbrl_as_of_date_estimated"


def test_merge_data_quality_flags_handles_comma_separated_string_input():
    merged = screener._merge_data_quality_flags("mock_history", "flag_a,flag_b")
    assert merged == "mock_history,flag_a,flag_b"


def test_merge_data_quality_flags_none_or_empty_is_a_noop():
    assert screener._merge_data_quality_flags("mock_history", None) == "mock_history"
    assert screener._merge_data_quality_flags("mock_history", []) == "mock_history"
    assert screener._merge_data_quality_flags("mock_history", "") == "mock_history"


def test_merge_data_quality_flags_empty_existing_with_flags():
    assert screener._merge_data_quality_flags("", ["a", "b"]) == "a,b"
    assert screener._merge_data_quality_flags(None, ["a", "b"]) == "a,b"


def test_merge_data_quality_flags_output_is_parseable_by_dq_gates_convention():
    # Round-trip through the exact helper dq_gates.py itself uses downstream,
    # confirming the two never disagree on format.
    from modules.data_layer.dq_gates import _append_flag

    merged = screener._merge_data_quality_flags(
        "mock_history", ["nse_xbrl_as_of_date_estimated", "extra_flag"]
    )
    # Appending yet another flag via dq_gates' own helper must not duplicate
    # or corrupt anything screener.py already produced.
    result = _append_flag(merged, "nse_xbrl_as_of_date_estimated")
    assert result == merged  # already present, no-op
    assert set(merged.split(",")) == {
        "mock_history",
        "nse_xbrl_as_of_date_estimated",
        "extra_flag",
    }
