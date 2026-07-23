"""
modules/liquidity.py
====================
Sovereign AI — Liquidity Intelligence v2

Phase 22: Live Liquidity Simulator
-----------------------------------
Replaces the static ADVT scorer with a full position-sizing / slippage
simulation engine.

Public surface
--------------
analyse_liquidity(stock_data)          → legacy 0-100 score (unchanged)
simulate_liquidity(stock_data, pos_cr) → LiquiditySimResult dataclass
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

# ────────────────────────────────────────────────────────────────────────────
# Tier thresholds (ADVT in Crores)
# ────────────────────────────────────────────────────────────────────────────

_ADVT_TIERS: list[tuple[float, int, str]] = [
    (100, 100, "Institutional Grade"),
    (50,   90, "HNI / Upper Retail"),
    (10,   80, "Retail Liquid"),
    (5,    70, "Watchlist OK"),
    (2,    50, "Moderate — size carefully"),
    (1,    30, "Low — risk-flag"),
    (0,     0, "Illiquid / Roach Motel"),
]


# ────────────────────────────────────────────────────────────────────────────
# Impact-cost model
# ────────────────────────────────────────────────────────────────────────────
# Based on an empirical square-root market-impact model used widely for
# Indian mid/small-cap universe:
#
#   impact_pct = k × sqrt(participation_rate)
#
# where k is calibrated from NSE tick data observations across ADVT bands.
# participation_rate = position_cr / advt_cr  (fraction of daily turnover)
#
# Additional spread component: bid-ask spread proxy via ATR / price.
# ────────────────────────────────────────────────────────────────────────────

# Impact coefficient per liquidity tier (higher = illiquid → more impact)
_K_BY_ADVT: list[tuple[float, float]] = [
    (100, 0.30),   # very liquid
    (50,  0.45),
    (10,  0.65),
    (5,   0.90),
    (2,   1.30),
    (1,   2.00),
    (0,   3.50),   # illiquid
]

# Days-to-build constraint: we cap participation at 20 % of daily volume
# per day (typical institutional limit for mid-caps in India).
_MAX_PARTICIPATION = 0.20

# Liquidity-at-risk horizon (days) for forced-exit scenario
_EXIT_HORIZON_DAYS = 5


def _impact_k(advt_cr: float) -> float:
    """Return the impact coefficient k for a given ADVT."""
    for threshold, k in _K_BY_ADVT:
        if advt_cr >= threshold:
            return k
    return _K_BY_ADVT[-1][1]


def _advt_score(advt_cr: float) -> tuple[int, bool, str]:
    """Map ADVT → (score, risk_flag, reason)."""
    for threshold, score, label in _ADVT_TIERS:
        if advt_cr >= threshold:
            risk_flag = advt_cr < 2
            reason = "" if advt_cr >= 5 else label
            return score, risk_flag, reason
    return 0, True, "Illiquid / Roach Motel (< 1Cr)"


# ────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class LiquiditySimResult:
    symbol: str

    # ── Input fields ──
    position_cr: float          # requested position size (₹ Crore)
    price: float
    avg_volume_10d: float
    atr: float | None

    # ── Derived liquidity metrics ──
    advt_cr: float              # Average Daily Value Traded (₹ Cr)
    spread_pct: float           # ATR-implied bid-ask spread estimate (%)
    liquidity_score: int        # 0-100 legacy score
    liquidity_tier: str         # human label
    risk_flag: bool

    # ── Position-size simulation ──
    participation_rate: float   # pos_cr / advt_cr  (0–1)
    days_to_build: float        # estimated sessions to build full position
    days_to_exit: float         # estimated sessions to fully exit (5-day VaR horizon)

    # ── Slippage estimates ──
    entry_slippage_pct: float   # one-way market impact on entry
    exit_slippage_pct: float    # one-way market impact on exit (conservative ×1.3)
    roundtrip_slippage_pct: float
    entry_slippage_cr: float    # slippage in ₹ Crore
    roundtrip_slippage_cr: float

    # ── Effective position sizing ──
    recommended_position_cr: float  # max position to keep entry slippage < 0.5 %
    max_safe_position_cr: float     # hard ceiling (1 % slippage tolerance)

    # ── Risk flags ──
    flags: list[str] = field(default_factory=list)

    # ── Overall verdict ──
    verdict: Literal["GREEN", "AMBER", "RED"] = "GREEN"
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "inputs": {
                "position_cr": self.position_cr,
                "price": self.price,
                "avg_volume_10d": self.avg_volume_10d,
                "atr": self.atr,
            },
            "liquidity": {
                "advt_cr": round(self.advt_cr, 2),
                "spread_pct": round(self.spread_pct, 3),
                "score": self.liquidity_score,
                "tier": self.liquidity_tier,
                "risk_flag": self.risk_flag,
            },
            "position_sizing": {
                "participation_rate": round(self.participation_rate, 4),
                "days_to_build": round(self.days_to_build, 1),
                "days_to_exit": round(self.days_to_exit, 1),
            },
            "slippage": {
                "entry_pct": round(self.entry_slippage_pct, 4),
                "exit_pct": round(self.exit_slippage_pct, 4),
                "roundtrip_pct": round(self.roundtrip_slippage_pct, 4),
                "entry_cr": round(self.entry_slippage_cr, 4),
                "roundtrip_cr": round(self.roundtrip_slippage_cr, 4),
            },
            "sizing_recommendation": {
                "recommended_position_cr": round(self.recommended_position_cr, 2),
                "max_safe_position_cr": round(self.max_safe_position_cr, 2),
            },
            "risk": {
                "verdict": self.verdict,
                "flags": self.flags,
                "summary": self.summary,
            },
        }


# ────────────────────────────────────────────────────────────────────────────
# Core simulator
# ────────────────────────────────────────────────────────────────────────────

def simulate_liquidity(stock_data: dict, position_cr: float) -> LiquiditySimResult:
    """
    Full liquidity simulation for a given position size.

    Parameters
    ----------
    stock_data : dict
        Must contain at least ``Price`` and ``Avg_Volume_10D``.
        Optional: ``ATR``, ``Market_Cap_Cr``, ``Symbol``.
    position_cr : float
        Intended position size in Indian Rupees Crore (₹ Cr).

    Returns
    -------
    LiquiditySimResult
        Rich dataclass with slippage estimates, sizing caps, and verdict.
    """
    symbol = stock_data.get("Symbol", stock_data.get("symbol", "UNKNOWN"))
    price = float(stock_data.get("Price", stock_data.get("price", 0)) or 0)
    avg_vol = float(stock_data.get("Avg_Volume_10D", stock_data.get("avg_volume_10d", 0)) or 0)
    atr_raw = stock_data.get("ATR", stock_data.get("atr", None))
    atr = float(atr_raw) if atr_raw is not None else None

    position_cr = max(position_cr, 0.0)

    # ── Guard: missing data ──
    if price <= 0 or avg_vol <= 0:
        return _zero_result(symbol, position_cr, price, avg_vol, atr,
                            "Price or Volume data unavailable")

    # ── ADVT ──
    advt_cr = (avg_vol * price) / 1e7          # volumes * price / 1 Cr divisor

    # ── Spread proxy (ATR-based) ──
    if atr and atr > 0:
        spread_pct = (atr / price) * 100 * 0.25  # ~25 % of ATR range = half-spread
    else:
        # fallback: scale inversely with liquidity
        spread_pct = max(0.05, 2.0 / (advt_cr + 0.1))

    spread_pct = min(spread_pct, 5.0)           # hard cap at 5 %

    # ── Legacy score ──
    score, risk_flag, reason = _advt_score(advt_cr)
    tier_label = next(
        (label for thresh, _, label in _ADVT_TIERS if advt_cr >= thresh), "Illiquid"
    )

    # ── Participation rate ──
    participation_rate = position_cr / advt_cr if advt_cr > 0 else float("inf")

    # ── Days to build / exit ──
    # Build: limited to _MAX_PARTICIPATION of daily volume each day
    if advt_cr > 0 and participation_rate > _MAX_PARTICIPATION:
        days_to_build = participation_rate / _MAX_PARTICIPATION
    else:
        days_to_build = 1.0 if participation_rate <= _MAX_PARTICIPATION else float("inf")

    # Exit horizon: same constraint but slightly worse (urgency premium)
    days_to_exit = max(
        days_to_build * 0.8,  # can often exit faster if willing to take loss
        position_cr / (advt_cr * _MAX_PARTICIPATION) if advt_cr > 0 else float("inf"),
    )
    days_to_exit = min(days_to_exit, 999.0)
    days_to_build = min(days_to_build, 999.0)

    # ── Market impact (square-root model) ──
    k = _impact_k(advt_cr)
    p = min(participation_rate, 5.0)           # cap to avoid absurd numbers for tiny stocks

    entry_impact_pct = k * math.sqrt(p) + spread_pct   # entry = impact + spread
    exit_impact_pct = entry_impact_pct * 1.30           # exit is conservative (forced)
    roundtrip_pct = entry_impact_pct + exit_impact_pct

    entry_slippage_cr = position_cr * entry_impact_pct / 100
    roundtrip_slippage_cr = position_cr * roundtrip_pct / 100

    # ── Safe sizing: back-solve for position_cr that keeps entry slippage ≤ threshold ──
    # entry_impact = k * sqrt(pos / advt) + spread
    # pos_recommended → entry_impact = 0.5 %
    # pos_max_safe    → entry_impact = 1.0 %

    def _max_pos_for_slippage(target_slippage_pct: float) -> float:
        """Return max position_cr such that entry impact ≤ target_slippage_pct.

        entry_impact = k * sqrt(pos / advt) + spread_pct
        Solving for pos: pos = advt * ((target - spread) / k)^2
        If spread_pct already ≥ target, there is no safe size → return 0.
        """
        headroom = target_slippage_pct - spread_pct
        if headroom <= 0 or k <= 0 or advt_cr <= 0:
            return 0.0
        return advt_cr * (headroom / k) ** 2

    recommended_position_cr = _max_pos_for_slippage(0.50)
    max_safe_position_cr = _max_pos_for_slippage(1.00)

    # ── Flags ──
    flags: list[str] = []

    if risk_flag:
        flags.append(f"ADVT {advt_cr:.2f} Cr is below institutional threshold (2 Cr)")

    if participation_rate > 0.10:
        flags.append(
            f"Position = {participation_rate*100:.1f}% of daily turnover — "
            "significant market impact expected"
        )

    if days_to_build > 5:
        flags.append(
            f"Estimated {days_to_build:.0f} trading sessions to fully build position "
            "at 20% daily participation cap"
        )

    if days_to_exit > _EXIT_HORIZON_DAYS:
        flags.append(
            f"Cannot exit within {_EXIT_HORIZON_DAYS}-day VaR horizon "
            f"({days_to_exit:.1f} sessions needed) — liquidity-at-risk"
        )

    if entry_impact_pct > 2.0:
        flags.append(
            f"Entry slippage estimate {entry_impact_pct:.2f}% exceeds 2% — "
            "consider reducing position size"
        )

    if position_cr > max_safe_position_cr * 1.5:
        flags.append(
            f"Requested ₹{position_cr:.1f} Cr far exceeds safe ceiling "
            f"₹{max_safe_position_cr:.1f} Cr for 1% slippage tolerance"
        )

    # ── Verdict ──
    # GREEN: pure market-impact component (excl. spread) is tiny and position
    # can be built quickly with no liquidity risk.
    impact_only_pct = entry_impact_pct - spread_pct  # impact cost ex-spread
    if impact_only_pct <= 0.30 and days_to_build <= 2 and not risk_flag:
        verdict: Literal["GREEN", "AMBER", "RED"] = "GREEN"
    elif entry_impact_pct <= 2.0 and days_to_exit <= _EXIT_HORIZON_DAYS:
        verdict = "AMBER"
    else:
        verdict = "RED"

    # ── Summary ──
    summary = (
        f"₹{position_cr:.1f} Cr position in {symbol} "
        f"({participation_rate*100:.1f}% of daily turnover): "
        f"estimated entry slippage {entry_impact_pct:.2f}%, "
        f"round-trip {roundtrip_pct:.2f}%. "
        f"Build over ~{days_to_build:.1f} session(s). "
        f"Safe sizing cap: ₹{recommended_position_cr:.1f} Cr (0.5% slippage)."
    )

    return LiquiditySimResult(
        symbol=symbol,
        position_cr=position_cr,
        price=price,
        avg_volume_10d=avg_vol,
        atr=atr,
        advt_cr=advt_cr,
        spread_pct=spread_pct,
        liquidity_score=score,
        liquidity_tier=tier_label,
        risk_flag=risk_flag,
        participation_rate=participation_rate,
        days_to_build=days_to_build,
        days_to_exit=days_to_exit,
        entry_slippage_pct=entry_impact_pct,
        exit_slippage_pct=exit_impact_pct,
        roundtrip_slippage_pct=roundtrip_pct,
        entry_slippage_cr=entry_slippage_cr,
        roundtrip_slippage_cr=roundtrip_slippage_cr,
        recommended_position_cr=recommended_position_cr,
        max_safe_position_cr=max_safe_position_cr,
        flags=flags,
        verdict=verdict,
        summary=summary,
    )


def _zero_result(symbol, position_cr, price, avg_vol, atr, reason) -> LiquiditySimResult:
    return LiquiditySimResult(
        symbol=symbol,
        position_cr=position_cr,
        price=price,
        avg_volume_10d=avg_vol,
        atr=atr,
        advt_cr=0.0,
        spread_pct=0.0,
        liquidity_score=0,
        liquidity_tier="Unknown",
        risk_flag=True,
        participation_rate=float("inf"),
        days_to_build=float("inf"),
        days_to_exit=float("inf"),
        entry_slippage_pct=0.0,
        exit_slippage_pct=0.0,
        roundtrip_slippage_pct=0.0,
        entry_slippage_cr=0.0,
        roundtrip_slippage_cr=0.0,
        recommended_position_cr=0.0,
        max_safe_position_cr=0.0,
        flags=[reason],
        verdict="RED",
        summary=reason,
    )


# ────────────────────────────────────────────────────────────────────────────
# Legacy shim — unchanged signature, unchanged return contract
# ────────────────────────────────────────────────────────────────────────────

def analyze_liquidity(stock_data: dict) -> tuple[int, bool, str]:
    """
    Phase 22: Liquidity & Slippage Intelligence (legacy shim).
    Analyses if a stock is liquid enough for institutional entry.

    Returns
    -------
    liquidity_score : int   0-100 (100 = Nifty-50 liquidity)
    risk_flag       : bool  True if liquidity is dangerously low
    reason          : str   Warning message
    """
    try:
        price = float(stock_data.get("Price", 0) or 0)
        avg_vol = float(stock_data.get("Avg_Volume_10D", 0) or 0)

        if price == 0 or avg_vol == 0:
            return 0, True, "No Volume Data"

        advt_cr = (avg_vol * price) / 1e7
        score, risk_flag, reason = _advt_score(advt_cr)

        # ATR-based impact cost flag (kept from original)
        atr = float(stock_data.get("ATR", 0) or 0)
        if atr and price and (atr / price) * 100 > 5 and risk_flag:
            reason = f"{reason} — High ATR volatility compounds slippage risk"

        if risk_flag:
            score = max(0, score - 20)

        return score, risk_flag, reason

    except Exception as exc:
        return 0, True, f"Error: {exc}"
