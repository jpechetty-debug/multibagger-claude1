"""Tests for AI Agent Panel — all LLM calls are mocked."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest

from modules.intelligence.agents.panel import (
    AgentSignal,
    ConsensusResult,
    _aggregate,
    _parse_signal,
    run_agent_panel,
)
from modules.intelligence.agents.personas import (
    AGENT_PANEL,
    build_prompt,
    package_stock_data,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_STOCK = {
    "Symbol": "TRENT",
    "Sector": "Retail",
    "Price": 5800,
    "Market_Cap_Cr": 205000,
    "total_score": 82.5,
    "rating": "A+",
    "F_Score": 8,
    "Sales_Growth_5Y%": 28.4,
    "Avg_ROE_5Y%": 18.7,
    "ROCE%": 22.1,
    "EPS_Growth%": 35.2,
    "CFO_PAT_Ratio": 1.1,
    "PE_Ratio": 95.0,
    "PEG_Ratio": 2.7,
    "Value_Gap%": -15.0,
    "Debt_Equity": 0.3,
    "Promoter_Holding%": 37.0,
    "Pledge_Pct": 0.0,
    "Inst_Holding%": 42.0,
    "Down_From_52W_High%": 8.0,
    "RS_Rating": 88,
    "ml_predicted_return": 22.5,
    "CAGR_Consistency": "HIGH",
}

VALID_JSON_RESPONSE = json.dumps({
    "verdict": "BUY",
    "conviction": 78,
    "confidence": 0.85,
    "reasoning": "28% sales CAGR with Tata pedigree is a compounder.",
    "key_concern": "PE of 95 is stretched.",
})

BEARISH_JSON = json.dumps({
    "verdict": "AVOID",
    "conviction": 25,
    "confidence": 0.9,
    "reasoning": "PE 95 offers no margin of safety.",
    "key_concern": "Extreme overvaluation.",
})


# ---------------------------------------------------------------------------
# Persona & data packaging tests
# ---------------------------------------------------------------------------

class TestPersonas:
    def test_all_personas_have_prompts(self):
        assert len(AGENT_PANEL) == 6
        for p in AGENT_PANEL:
            assert p.name
            assert p.system_prompt
            assert len(p.focus_metrics) >= 3

    def test_build_prompt_returns_two_strings(self):
        system, user = build_prompt(AGENT_PANEL[0], SAMPLE_STOCK)
        assert "Indian Equity Markets" in system
        assert "TRENT" in user
        assert "verdict" in user  # response schema

    def test_package_handles_missing_fields(self):
        sparse = {"Symbol": "XYZ"}
        text = package_stock_data(sparse)
        assert "XYZ" in text
        assert "?" in text  # Missing values show ?


# ---------------------------------------------------------------------------
# Signal parsing tests
# ---------------------------------------------------------------------------

class TestParsing:
    def test_valid_json(self):
        sig = _parse_signal("Test", VALID_JSON_RESPONSE)
        assert sig.verdict == "BUY"
        assert sig.conviction == 78
        assert sig.confidence == 0.85
        assert "28%" in sig.reasoning

    def test_json_in_markdown(self):
        raw = f"Here is my analysis:\n```json\n{VALID_JSON_RESPONSE}\n```\n"
        sig = _parse_signal("Test", raw)
        assert sig.verdict == "BUY"

    def test_malformed_response(self):
        sig = _parse_signal("Test", "I think this stock is great!")
        assert sig.verdict == "HOLD"
        assert sig.conviction == 50

    def test_invalid_verdict_normalised(self):
        raw = json.dumps({"verdict": "STRONG BUY", "conviction": 90})
        sig = _parse_signal("Test", raw)
        assert sig.verdict == "HOLD"  # Invalid → fallback

    def test_conviction_clamped(self):
        raw = json.dumps({"verdict": "BUY", "conviction": 150, "confidence": 2.0})
        sig = _parse_signal("Test", raw)
        assert sig.conviction == 100
        assert sig.confidence == 1.0

    def test_empty_response(self):
        sig = _parse_signal("Test", "")
        assert sig.verdict == "HOLD"


# ---------------------------------------------------------------------------
# Consensus aggregation tests
# ---------------------------------------------------------------------------

def _make_signal(name: str, verdict: str, conviction: int, confidence: float = 0.8,
                 concern: str = "") -> AgentSignal:
    return AgentSignal(
        agent_name=name, verdict=verdict, conviction=conviction,
        confidence=confidence, reasoning=f"{name} says {verdict}",
        key_concern=concern,
    )


class TestConsensus:
    def test_all_bullish(self):
        signals = [_make_signal(f"Agent{i}", "BUY", 80) for i in range(6)]
        result = _aggregate(signals, SAMPLE_STOCK)
        assert result.ai_verdict == "BUY"
        assert result.ai_consensus_score >= 75
        assert result.agreement_ratio == 1.0
        assert result.position_modifier == 1.0

    def test_all_bearish(self):
        signals = [_make_signal(f"Agent{i}", "AVOID", 20) for i in range(6)]
        result = _aggregate(signals, SAMPLE_STOCK)
        assert result.ai_verdict == "AVOID"
        assert result.ai_consensus_score <= 25

    def test_split_opinion(self):
        signals = (
            [_make_signal(f"Bull{i}", "BUY", 75) for i in range(3)]
            + [_make_signal(f"Bear{i}", "AVOID", 30) for i in range(3)]
        )
        result = _aggregate(signals, SAMPLE_STOCK)
        assert result.ai_verdict == "HOLD"
        assert result.agreement_ratio == 0.5
        assert result.position_modifier == 0.75  # 0.5 falls in >= 0.5 branch

    def test_confidence_weighting(self):
        signals = [
            _make_signal("HighConf", "BUY", 90, confidence=0.95),
            _make_signal("LowConf", "AVOID", 20, confidence=0.1),
        ]
        result = _aggregate(signals, SAMPLE_STOCK)
        # High-confidence bull should dominate
        assert result.ai_consensus_score > 70

    def test_risk_override_pledge(self):
        pledged_stock = {**SAMPLE_STOCK, "Pledge_Pct": 45.0}
        signals = [_make_signal(f"Agent{i}", "BUY", 85) for i in range(6)]
        result = _aggregate(signals, pledged_stock)
        assert result.ai_verdict == "AVOID"  # Forced override
        assert any("PLEDGE_DEALBREAKER" in f for f in result.risk_flags)
        assert result.position_modifier <= 0.25

    def test_risk_flags_collected(self):
        signals = [
            _make_signal("Risk Analyst", "AVOID", 30, concern="Auditor changed twice in 2 years"),
            _make_signal("Other", "BUY", 80),
        ]
        result = _aggregate(signals, SAMPLE_STOCK)
        assert "Auditor changed" in result.risk_flags[0]

    def test_empty_signals(self):
        result = _aggregate([], SAMPLE_STOCK)
        assert result.ai_consensus_score == 50.0


# ---------------------------------------------------------------------------
# Integration tests (mocked Ollama)
# ---------------------------------------------------------------------------

class TestPanel:
    @patch("modules.intelligence.agents.panel._call_ollama")
    def test_full_panel_run(self, mock_ollama):
        mock_ollama.return_value = VALID_JSON_RESPONSE
        results = asyncio.run(run_agent_panel([SAMPLE_STOCK]))

        assert "TRENT" in results
        r = results["TRENT"]
        assert isinstance(r, ConsensusResult)
        assert r.ai_consensus_score > 0
        assert mock_ollama.call_count == 6  # 6 agents

    @patch("modules.intelligence.agents.panel._call_ollama")
    def test_ollama_failure_graceful(self, mock_ollama):
        mock_ollama.side_effect = ConnectionError("Ollama down")
        results = asyncio.run(run_agent_panel([SAMPLE_STOCK]))

        assert "TRENT" in results
        r = results["TRENT"]
        assert r.ai_consensus_score == 50.0  # Neutral fallback

    @patch("modules.intelligence.agents.panel._call_ollama")
    def test_empty_input(self, mock_ollama):
        results = asyncio.run(run_agent_panel([]))
        assert results == {}
        mock_ollama.assert_not_called()

    @patch("modules.intelligence.agents.panel._call_ollama")
    def test_multiple_stocks(self, mock_ollama):
        mock_ollama.return_value = BEARISH_JSON
        stock2 = {**SAMPLE_STOCK, "Symbol": "ZOMATO"}
        results = asyncio.run(run_agent_panel([SAMPLE_STOCK, stock2]))

        assert len(results) == 2
        assert "TRENT" in results
        assert "ZOMATO" in results

    @patch("modules.intelligence.agents.panel._call_ollama")
    def test_timeout_per_stock(self, mock_ollama):
        async def slow(*args, **kwargs):
            await asyncio.sleep(10)
            return VALID_JSON_RESPONSE

        mock_ollama.side_effect = lambda *a, **k: (_ for _ in ()).throw(
            TimeoutError("Too slow")
        )

        results = asyncio.run(run_agent_panel([SAMPLE_STOCK], timeout=1.0))
        r = results["TRENT"]
        assert r.ai_consensus_score == 50.0  # Graceful fallback
