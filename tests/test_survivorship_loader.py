from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backtest.survivorship_adjusted_loader import SurvivorshipAdjustedLoader


def _make_workspace_tmpdir() -> Path:
    path = ROOT / "runtime" / "test_survivorship_loader"
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_survivorship_loader_filters_listing_and_delisting_dates():
    temp_dir = _make_workspace_tmpdir()
    try:
        listing_path = temp_dir / "nse_listing_dates.csv"
        pd.DataFrame(
            [
                {"Symbol": "RELIANCE", "Listing_Date": "1977-07-08", "Delisting_Date": ""},
                {"Symbol": "RCOM", "Listing_Date": "2004-03-01", "Delisting_Date": "2020-06-01"},
                {"Symbol": "NEWCO", "Listing_Date": "2021-01-15", "Delisting_Date": ""},
            ]
        ).to_csv(listing_path, index=False)

        loader = SurvivorshipAdjustedLoader(data_dir=str(temp_dir))

        march_2020 = loader.get_universe("2020-03-01", ["RELIANCE", "RCOM", "NEWCO"])
        july_2020 = loader.get_universe("2020-07-01", ["RELIANCE", "RCOM", "NEWCO"])

        assert march_2020 == ["RELIANCE", "RCOM"]
        assert july_2020 == ["RELIANCE"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_survivorship_loader_prefers_snapshot_when_available():
    temp_dir = _make_workspace_tmpdir()
    try:
        snapshot_path = temp_dir / "nifty500_2020-03.csv"
        pd.DataFrame([{"Symbol": "TCS"}, {"Symbol": "INFY"}]).to_csv(snapshot_path, index=False)

        loader = SurvivorshipAdjustedLoader(data_dir=str(temp_dir))
        result = loader.get_universe("2020-03-15", ["TCS", "INFY", "RELIANCE"])

        assert result == ["TCS", "INFY"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
