from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import brain.garp_strategy as garp_module
from brain.garp_strategy import GarpStrategy


async def _noop_news_fetch(self, proposals):
    return proposals


def test_garp_strategy_uses_nexus_score_as_primary_rank(monkeypatch):
    strategy = GarpStrategy()
    strategy.universe = pd.DataFrame(
        [
            {
                "symbol": "ALPHA.NS",
                "score": 92,
                "conviction_score": 48,
                "rs_rating": 1.0,
                "data_quality": 90,
                "price": 100,
            },
            {
                "symbol": "BETA.NS",
                "score": 55,
                "conviction_score": 96,
                "rs_rating": 3.0,
                "data_quality": 92,
                "price": 100,
            },
        ]
    )

    monkeypatch.setattr(GarpStrategy, "load_universe", lambda self: None)
    monkeypatch.setattr(garp_module, "validate_garp_criteria", lambda stock: (True, "Passed"))
    monkeypatch.setattr(GarpStrategy, "_fetch_news_batch", _noop_news_fetch)

    proposals = strategy.generate_proposals(top_n=2)

    assert [row["Symbol"] for row in proposals] == ["ALPHA.NS", "BETA.NS"]
    assert proposals[0]["Nexus_Score"] == 92.0
    assert proposals[0]["Rank_Score"] > proposals[1]["Rank_Score"]


def test_garp_strategy_falls_back_to_conviction_when_nexus_score_missing():
    components = GarpStrategy._build_rank_components(
        {
            "conviction_score": 80,
            "rs_rating": 3.0,
            "data_quality": 70,
        }
    )

    assert components["nexus_score"] == 0.0
    assert components["rank_score"] == 86.0
