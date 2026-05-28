"""Integration tests for SurvivorshipAdjustedLoader.

Tests:
  - Priority 3 fallback emits warnings.warn (not just logger)
  - RCOM excluded after delisting date
  - Boundary: exact delisting date excludes the stock
  - Real CSV canary (backtest marker, skips if CSV missing)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.survivorship_adjusted_loader import SurvivorshipAdjustedLoader


class TestSurvivorshipIntegration:

    def test_priority3_emits_warnings_warn(self, tmp_path, recwarn):
        """Priority 3 fallback must emit a warnings.warn, not just log."""
        loader = SurvivorshipAdjustedLoader(data_dir=str(tmp_path))
        loader.get_universe("2020-01-01", candidates=["RELIANCE", "TCS"])
        assert any("SURVIVORSHIP BIAS" in str(w.message) for w in recwarn.list)

    def test_rcom_excluded_after_delisting(self, tmp_path):
        """RCOM delisted 2020-06-01 — must not appear in universe after that date."""
        csv = tmp_path / "nse_listing_dates.csv"
        pd.DataFrame([
            {"Symbol": "RELIANCE", "Listing_Date": "1977-07-08", "Delisting_Date": ""},
            {"Symbol": "RCOM", "Listing_Date": "2004-03-01", "Delisting_Date": "2020-06-01"},
        ]).to_csv(csv, index=False)
        loader = SurvivorshipAdjustedLoader(data_dir=str(tmp_path))
        pre = loader.get_universe("2019-12-01", candidates=["RELIANCE", "RCOM"])
        post = loader.get_universe("2021-01-01", candidates=["RELIANCE", "RCOM"])
        assert "RCOM" in pre
        assert "RCOM" not in post
        assert "RELIANCE" in post

    def test_rcom_excluded_boundary_exact_delisting_date(self, tmp_path):
        """On the exact delisting date, the stock is excluded."""
        csv = tmp_path / "nse_listing_dates.csv"
        pd.DataFrame([
            {"Symbol": "RCOM", "Listing_Date": "2004-03-01", "Delisting_Date": "2020-06-01"},
        ]).to_csv(csv, index=False)
        loader = SurvivorshipAdjustedLoader(data_dir=str(tmp_path))
        # Day before: included
        assert "RCOM" in loader.get_universe("2020-05-31", candidates=["RCOM"])
        # Exact date: excluded (Delisting_Date > target, so equal means excluded)
        assert "RCOM" not in loader.get_universe("2020-06-01", candidates=["RCOM"])

    @pytest.mark.backtest
    def test_real_csv_present_and_covers_known_stocks(self):
        """Integration — only runs when data/nse_listing_dates.csv is committed."""
        csv = Path("data/nse_listing_dates.csv")
        if not csv.exists():
            pytest.skip("data/nse_listing_dates.csv not present — run fetch script")
        loader = SurvivorshipAdjustedLoader(data_dir="data")
        nifty50 = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
        universe = loader.get_universe("2023-01-01", candidates=nifty50)
        assert len(universe) == len(nifty50), \
            f"Expected all Nifty 50 blue chips active in Jan 2023, got: {universe}"
