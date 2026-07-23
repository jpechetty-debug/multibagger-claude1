# tests/test_none_safety_regression.py
"""
Phase 1 Fix: Regression test ensuring None-safety in the scoring pipeline.

Validates that the v25-v26 safe_float() refactor remains intact and no
raw `.get(key, 0) > threshold` patterns have crept back in.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# All optional numeric fields used in the scoring pipeline
_ALL_OPTIONAL_FIELDS = [
    "PE_Ratio", "PEG_Ratio", "Debt_Equity", "CFO_PAT_Ratio",
    "Sales_Growth_5Y%", "Sales_Growth_TTM%", "EPS_Growth%",
    "Avg_ROE_5Y%", "ROE%", "Profit_Margin%", "Value_Gap%",
    "Market_Cap_Cr", "Down_From_52W_High%", "Analyst_Upside%",
    "Estimate_Score_Adj", "Earnings_Inflection_Score",
    "Inst_Holding%", "Promoter_Holding%", "F_Score", "RS_Rating",
    "Price", "ATR", "Earnings_Accel", "Technical_Signal",
    "Analyst_Rating", "CAGR_Consistency",
]


def _build_minimal_stock_data(**overrides):
    """Build a stock data dict with only Symbol and Sector."""
    base = {"Symbol": "TEST.NS", "Sector": "Technology"}
    base.update(overrides)
    return base


class TestNoneSafetyRegression:
    """Ensure scoring pipeline never crashes on None inputs."""

    def test_all_fields_none_no_crash(self):
        """Scoring with every optional field set to None must not crash."""
        from modules.scoring import calculate_institutional_score

        data = _build_minimal_stock_data(
            **dict.fromkeys(_ALL_OPTIONAL_FIELDS)
        )
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)
        assert 0 <= result["total_score"] <= 100

    def test_all_fields_nan_no_crash(self):
        """Scoring with every numeric field set to NaN must not crash."""
        from modules.scoring import calculate_institutional_score

        nan_fields = {
            field: float("nan")
            for field in _ALL_OPTIONAL_FIELDS
            if field not in ("Symbol", "Sector", "Technical_Signal",
                             "Analyst_Rating", "CAGR_Consistency")
        }
        data = _build_minimal_stock_data(**nan_fields)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)

    def test_all_fields_string_garbage_no_crash(self):
        """Scoring with string garbage in numeric fields must not crash."""
        from modules.scoring import calculate_institutional_score

        garbage_fields = {
            field: "not-a-number"
            for field in _ALL_OPTIONAL_FIELDS
            if field not in ("Symbol", "Sector")
        }
        data = _build_minimal_stock_data(**garbage_fields)
        result = calculate_institutional_score(data)
        assert isinstance(result["total_score"], int | float)

    def test_empty_dict_no_crash(self):
        """Scoring with only Symbol should not crash."""
        from modules.scoring import calculate_institutional_score

        result = calculate_institutional_score({"Symbol": "EMPTY.NS"})
        assert isinstance(result["total_score"], int | float)

    def test_safe_float_none_returns_zero(self):
        from modules.data_utils import safe_float

        assert safe_float(None) == 0.0

    def test_safe_float_nan_returns_default(self):
        from modules.data_utils import safe_float

        assert safe_float(float("nan"), default=7.0) == 7.0

    def test_optional_float_none_returns_none(self):
        from modules.data_utils import optional_float

        assert optional_float(None) is None

    def test_optional_float_inf_returns_none(self):
        from modules.data_utils import optional_float

        assert optional_float(float("inf")) is None


class TestNoRawGetPatterns:
    """Verify no unsafe .get(key, 0) > threshold patterns in scoring code."""

    def test_no_raw_get_with_default_zero_comparison(self):
        """Grep-style check: no '.get(key, 0) >' patterns in scoring modules."""
        import re

        scoring_dir = ROOT / "modules" / "scoring"
        pattern = re.compile(r'data\.get\([^)]+,\s*0\)\s*[><=!]')

        violations = []
        for py_file in scoring_dir.glob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                if pattern.search(line):
                    violations.append(f"{py_file.name}:{i}: {line.strip()}")

        assert not violations, (
            "Raw .get(key, 0) > threshold patterns found (use safe_float):\n"
            + "\n".join(violations)
        )
