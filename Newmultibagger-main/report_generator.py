from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff

PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = str(PROJECT_ROOT / "data" / "report_cache")


def _cache_key(symbol: str) -> str:
    normalized = symbol.strip().upper()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _signature_path(path: Path) -> Path:
    return Path(str(path) + ".sha256")


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _read_verified_cache(path: Path) -> str | None:
    sig_path = _signature_path(path)
    if not path.exists() or not sig_path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    expected = sig_path.read_text(encoding="utf-8").strip()
    if expected == _sha256(content):
        return content
    return None


def _write_verified_cache(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _signature_path(path).write_text(_sha256(content), encoding="utf-8")


def _fmt_money(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if numeric >= 10_000_000:
        return f"{numeric / 10_000_000:.2f} cr"
    return f"{numeric:.2f}"


def _fmt_pct(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if abs(numeric) <= 1:
        numeric *= 100
    return f"{numeric:.2f}%"


def _render_report(symbol: str, info: dict[str, Any]) -> str:
    name = info.get("longName") or info.get("shortName") or symbol
    current_price = _fmt_money(info.get("currentPrice"))
    market_cap = _fmt_money(info.get("marketCap"))
    target_price = _fmt_money(info.get("targetMeanPrice"))
    roe = _fmt_pct(info.get("returnOnEquity"))
    margins = _fmt_pct(info.get("profitMargins"))

    return "\n".join(
        [
            f"# Analyst Report: {symbol}",
            "",
            f"Company: {name}",
            f"Current price: {current_price}",
            f"Market cap: {market_cap}",
            f"Trailing PE: {info.get('trailingPE', 'N/A')}",
            f"Return on equity: {roe}",
            f"Debt to equity: {info.get('debtToEquity', 'N/A')}",
            f"Profit margin: {margins}",
            f"52-week high: {_fmt_money(info.get('fiftyTwoWeekHigh'))}",
            f"Analyst view: {info.get('recommendationKey', 'N/A')}",
            f"Target mean price: {target_price}",
            "",
            "## Snapshot",
            (
                "This report is generated from the latest available market metadata "
                "and cached with a checksum so stale or tampered cache entries are rebuilt."
            ),
        ]
    )


async def generate_analyst_report(symbol: str) -> str:
    normalized = symbol.strip().upper()
    cache_path = Path(CACHE_DIR) / f"{_cache_key(normalized)}.md"

    cached = _read_verified_cache(cache_path)
    if cached is not None:
        return cached

    info = await run_with_exponential_backoff(
        lambda: yf.Ticker(normalized).info,
        context=f"{normalized} analyst report",
    )
    if not isinstance(info, dict):
        info = {}

    report = _render_report(normalized, info)
    _write_verified_cache(cache_path, report)
    return report
