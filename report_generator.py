from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff

CACHE_DIR = "reports_cache"


def _cache_key(symbol: str) -> str:
    return str(symbol or "").strip().upper().replace("/", "_").replace("\\", "_")


def _signature_path(path: Path) -> Path:
    return Path(str(path) + ".sha256")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_verified_cache(path: Path) -> str | None:
    sig_path = _signature_path(path)
    if not path.exists() or not sig_path.exists():
        return None

    content = path.read_text(encoding="utf-8")
    expected = sig_path.read_text(encoding="utf-8").strip()
    if expected == _sha256(content):
        return content
    return None


def _write_signed_cache(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _signature_path(path).write_text(_sha256(content), encoding="utf-8")


def _fmt(value: Any, default: str = "N/A") -> str:
    if value is None:
        return default
    return str(value)


def _build_report(symbol: str, info: dict[str, Any]) -> str:
    name = info.get("longName") or info.get("shortName") or symbol
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    market_cap_cr = None
    if info.get("marketCap"):
        market_cap_cr = round(float(info["marketCap"]) / 10_000_000, 2)

    roe = info.get("returnOnEquity")
    if isinstance(roe, (int, float)):
        roe = round(roe * 100, 2)

    debt_equity = info.get("debtToEquity")
    pe = info.get("trailingPE")
    target = info.get("targetMeanPrice")
    rating = str(info.get("recommendationKey") or "none").replace("_", " ").title()
    analyst_count = info.get("numberOfAnalystOpinions")

    return "\n".join(
        [
            f"# Sovereign Analyst Report: {symbol}",
            "",
            "## Company",
            f"- Name: {_fmt(name)}",
            f"- Current Price: {_fmt(price)}",
            f"- Market Cap Cr: {_fmt(market_cap_cr)}",
            "",
            "## Quality And Valuation",
            f"- P/E: {_fmt(pe)}",
            f"- ROE %: {_fmt(roe)}",
            f"- Debt/Equity: {_fmt(debt_equity)}",
            f"- Profit Margin: {_fmt(info.get('profitMargins'))}",
            "",
            "## Street View",
            f"- Consensus: {_fmt(rating)}",
            f"- Target Mean Price: {_fmt(target)}",
            f"- Analyst Count: {_fmt(analyst_count)}",
            "",
            "## Cash And Ownership",
            f"- Operating Cash Flow: {_fmt(info.get('operatingCashflow'))}",
            f"- Net Income: {_fmt(info.get('netIncomeToCommon'))}",
            f"- Insider Holding: {_fmt(info.get('heldPercentInsiders'))}",
            f"- Institution Holding: {_fmt(info.get('heldPercentInstitutions'))}",
            "",
        ]
    )


async def generate_analyst_report(symbol: str) -> str:
    normalized_symbol = str(symbol or "").strip().upper()
    cache_path = Path(CACHE_DIR) / f"{_cache_key(normalized_symbol)}.md"

    cached = _read_verified_cache(cache_path)
    if cached is not None:
        return cached

    ticker = yf.Ticker(normalized_symbol)
    info = await run_with_exponential_backoff(
        lambda: ticker.info,
        context=f"analyst report {normalized_symbol}",
    )
    if not isinstance(info, dict):
        info = {}

    report = _build_report(normalized_symbol, info)
    _write_signed_cache(cache_path, report)
    return report
