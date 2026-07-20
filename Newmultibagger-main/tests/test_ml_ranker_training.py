from __future__ import annotations

from modules import ml_ranker


def test_ranker_training_uses_automated_training_orchestration(monkeypatch):
    """The compatibility adapter retains ML bootstrap fallback behaviour."""
    calls: list[bool] = []

    def fake_run_automated_training() -> bool:
        calls.append(True)
        return True

    monkeypatch.setattr(ml_ranker, "run_automated_training", fake_run_automated_training)

    assert ml_ranker.LightGBMRanker().train() is True
    assert calls == [True]
