"""
AI Agent Panel — conviction gate for top-N stocks.

Runs 6 India-focused persona agents against pre-scored candidates via Ollama.
Returns consensus scores, verdicts, and reasoning for IC Memo enrichment.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests

import config
from core.observability.logger import get_logger

from .personas import AGENT_PANEL, Persona, build_prompt

_log = get_logger("intelligence.agents.panel")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

_VALID_VERDICTS = {"BUY", "HOLD", "AVOID"}
_NEUTRAL_CONVICTION = 50
_NEUTRAL_CONFIDENCE = 0.5


@dataclass
class AgentSignal:
    agent_name: str
    verdict: str = "HOLD"
    conviction: int = _NEUTRAL_CONVICTION
    confidence: float = _NEUTRAL_CONFIDENCE
    reasoning: str = ""
    key_concern: str = ""


@dataclass
class ConsensusResult:
    ai_consensus_score: float = 50.0
    ai_verdict: str = "HOLD"
    bull_count: int = 0
    bear_count: int = 0
    agreement_ratio: float = 0.5
    position_modifier: float = 1.0
    agent_signals: list[AgentSignal] = field(default_factory=list)
    combined_reasoning: str = ""
    risk_flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def _parse_signal(agent_name: str, raw: str) -> AgentSignal:
    """Extract structured signal from LLM text. Graceful fallback on failure."""
    try:
        # Try to find JSON object in response
        match = _JSON_RE.search(raw)
        if not match:
            raise ValueError("No JSON found")
        data = json.loads(match.group())

        verdict = str(data.get("verdict", "HOLD")).upper().strip()
        if verdict not in _VALID_VERDICTS:
            verdict = "HOLD"

        conviction = int(data.get("conviction", _NEUTRAL_CONVICTION))
        conviction = max(0, min(100, conviction))

        confidence = float(data.get("confidence", _NEUTRAL_CONFIDENCE))
        confidence = max(0.0, min(1.0, confidence))

        return AgentSignal(
            agent_name=agent_name,
            verdict=verdict,
            conviction=conviction,
            confidence=confidence,
            reasoning=str(data.get("reasoning", ""))[:500],
            key_concern=str(data.get("key_concern", ""))[:200],
        )
    except Exception as exc:
        _log.warning(f"Failed to parse signal from {agent_name}: {exc}")
        return AgentSignal(agent_name=agent_name)


# ---------------------------------------------------------------------------
# LLM call (sync, to be run in thread pool)
# ---------------------------------------------------------------------------

_OLLAMA_URL: str = config.OLLAMA_URL
_MODEL: str = getattr(config, "AGENT_PANEL_MODEL", "deepseek-r1:32b")
_TIMEOUT: float = getattr(config, "AGENT_PANEL_TIMEOUT", 90.0)


def _call_ollama(system: str, user: str) -> str:
    """Blocking Ollama call. Returns raw response text."""
    resp = requests.post(
        _OLLAMA_URL,
        json={
            "model": _MODEL,
            "system": system,
            "prompt": user,
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 300},
        },
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json().get("response", "")


async def _query_agent(persona: Persona, stock_data: dict[str, Any]) -> AgentSignal:
    """Run a single agent asynchronously via thread pool."""
    system, user = build_prompt(persona, stock_data)
    try:
        raw = await asyncio.to_thread(_call_ollama, system, user)
        return _parse_signal(persona.name, raw)
    except Exception as exc:
        _log.warning(f"{persona.name} failed for {stock_data.get('Symbol', '?')}: {exc}")
        return AgentSignal(agent_name=persona.name)


# ---------------------------------------------------------------------------
# Consensus aggregation
# ---------------------------------------------------------------------------

_PLEDGE_DEALBREAKER = 40.0  # Risk override threshold


def _aggregate(signals: list[AgentSignal], stock_data: dict[str, Any]) -> ConsensusResult:
    """Confidence-weighted consensus from agent signals."""
    if not signals:
        return ConsensusResult()

    # Confidence-weighted score
    total_weight = sum(s.confidence for s in signals) or 1.0
    weighted_score = sum(s.conviction * s.confidence for s in signals) / total_weight

    bulls = sum(1 for s in signals if s.verdict == "BUY")
    bears = sum(1 for s in signals if s.verdict == "AVOID")

    # Verdict by majority
    if bulls >= 4:
        verdict = "BUY"
    elif bears >= 4:
        verdict = "AVOID"
    else:
        verdict = "HOLD"

    agreement = max(bulls, bears) / len(signals)

    # Position modifier based on agreement
    if agreement > 0.8:
        modifier = 1.0
    elif agreement >= 0.5:
        modifier = 0.75
    else:
        modifier = 0.5

    # Collect risk flags from Risk Analyst
    risk_flags: list[str] = []
    for s in signals:
        if s.agent_name == "Risk Analyst" and s.key_concern:
            risk_flags.append(s.key_concern)

    # Risk override: pledge dealbreaker
    pledge = stock_data.get("Pledge_Pct") or stock_data.get("pledge_pct") or 0
    try:
        pledge = float(pledge)
    except (TypeError, ValueError):
        pledge = 0.0
    if pledge > _PLEDGE_DEALBREAKER:
        verdict = "AVOID"
        risk_flags.insert(0, f"PLEDGE_DEALBREAKER: {pledge:.1f}%")
        modifier = min(modifier, 0.25)

    # Build combined reasoning
    reasoning_parts = [
        f"**{s.agent_name}** ({s.verdict}): {s.reasoning}"
        for s in signals if s.reasoning
    ]

    return ConsensusResult(
        ai_consensus_score=round(max(0, min(100, weighted_score)), 1),
        ai_verdict=verdict,
        bull_count=bulls,
        bear_count=bears,
        agreement_ratio=round(agreement, 2),
        position_modifier=modifier,
        agent_signals=signals,
        combined_reasoning="\n\n".join(reasoning_parts),
        risk_flags=risk_flags,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_CONCURRENCY = 3  # Max parallel Ollama calls


async def _evaluate_stock(
    stock_data: dict[str, Any],
    agents: tuple[Persona, ...] = AGENT_PANEL,
    semaphore: asyncio.Semaphore | None = None,
) -> ConsensusResult:
    """Run all agents for a single stock."""
    sem = semaphore or asyncio.Semaphore(_CONCURRENCY)

    async def _guarded(persona: Persona) -> AgentSignal:
        async with sem:
            return await _query_agent(persona, stock_data)

    signals = await asyncio.gather(*[_guarded(p) for p in agents])
    return _aggregate(list(signals), stock_data)


async def run_agent_panel(
    top_stocks: list[dict[str, Any]],
    agents: tuple[Persona, ...] = AGENT_PANEL,
    timeout: float = 300.0,
) -> dict[str, ConsensusResult]:
    """
    Run the India AI Agent Panel on pre-scored top-N stocks.

    Args:
        top_stocks: List of scored stock dicts (must contain 'Symbol').
        agents: Persona tuple to use (defaults to full India panel).
        timeout: Max wall-clock seconds for entire panel run.

    Returns:
        {symbol: ConsensusResult} mapping.
    """
    if not top_stocks:
        return {}

    sem = asyncio.Semaphore(_CONCURRENCY)
    results: dict[str, ConsensusResult] = {}
    t0 = time.monotonic()

    _log.info(
        f"Agent panel: evaluating {len(top_stocks)} stocks "
        f"with {len(agents)} agents (concurrency={_CONCURRENCY})"
    )

    # Try to use Redis cache for dedup within same day
    cache = _get_cache()

    for stock in top_stocks:
        symbol = stock.get("Symbol", stock.get("symbol", "UNKNOWN"))
        cache_key = f"agent_panel:{symbol}:{time.strftime('%Y-%m-%d')}"

        # Check cache
        cached = cache.get(cache_key) if cache else None
        if cached and isinstance(cached, dict):
            _log.debug(f"Cache hit for {symbol}")
            results[symbol] = ConsensusResult(**cached)
            continue

        # Evaluate
        try:
            remaining = timeout - (time.monotonic() - t0)
            if remaining <= 0:
                _log.warning("Agent panel timeout — skipping remaining stocks")
                break
            result = await asyncio.wait_for(
                _evaluate_stock(stock, agents, sem),
                timeout=remaining,
            )
            results[symbol] = result

            # Cache result
            if cache:
                _cache_result(cache, cache_key, result)

        except asyncio.TimeoutError:
            _log.warning(f"Timeout evaluating {symbol}")
            results[symbol] = ConsensusResult()
        except Exception as exc:
            _log.error(f"Agent panel error for {symbol}: {exc}")
            results[symbol] = ConsensusResult()

    elapsed = time.monotonic() - t0
    _log.info(f"Agent panel complete: {len(results)} stocks in {elapsed:.1f}s")
    return results


# ---------------------------------------------------------------------------
# Cache helpers (best-effort, non-blocking)
# ---------------------------------------------------------------------------

def _get_cache():
    """Get Redis cache instance, or None if unavailable."""
    try:
        from worker.redis_cache import cache
        if cache.is_connected():
            return cache
    except Exception:
        pass
    return None


def _cache_result(cache, key: str, result: ConsensusResult) -> None:
    """Store consensus result in Redis with 24h TTL."""
    try:
        data = {
            "ai_consensus_score": result.ai_consensus_score,
            "ai_verdict": result.ai_verdict,
            "bull_count": result.bull_count,
            "bear_count": result.bear_count,
            "agreement_ratio": result.agreement_ratio,
            "position_modifier": result.position_modifier,
            "combined_reasoning": result.combined_reasoning,
            "risk_flags": result.risk_flags,
            # Skip agent_signals for cache (too large, not needed for re-hydration)
        }
        cache.set(key, data, ttl=86400)  # 24 hours
    except Exception as exc:
        _log.debug(f"Cache write failed: {exc}")
