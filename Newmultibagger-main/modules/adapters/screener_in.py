"""Screener.in free data adapter for Indian equity fundamentals.

Screener.in (https://www.screener.in) provides free access to 10+ years of
financial data for all NSE/BSE listed companies. No API key or subscription
required — data is scraped from the public HTML pages.

What this adapter provides (not available from yFinance for Indian stocks):
  - 5Y/10Y Sales CAGR and Profit CAGR  ← computed from actual P&L tables
  - ROCE (Return on Capital Employed)
  - CFO/PAT ratio (cash quality indicator)
  - Quarterly result announcement date → pub_date for PIT enforcement
  - Promoter holding %
  - NSE-authoritative sector classification
  - Piotroski F-Score computed from actual balance sheet

Cloudflare bypass:
  Screener.in uses Cloudflare. This adapter uses curl_cffi with
  impersonate="chrome110" to bypass the JS challenge — the same approach
  already used by PNSEAProvider in modules/adapters/nse.py.

Rate limiting:
  This adapter is a guest on Screener.in's infrastructure. It enforces
  a minimum 2-second delay between requests per process (SCREENER_MIN_DELAY_S).
  Aggressive scraping will get the IP blocked. The cache layer (Redis or
  in-memory) in data_service.py means each symbol is only fetched once
  per cache TTL (default 4 hours).

Usage in data_service.py:
  Insert ScreenerInProvider at Priority 2 in the provider chain — after
  PNSEAProvider (for real-time price) but before NSEPythonProvider.
  It is only instantiated when curl_cffi is available (soft dependency).
"""

from __future__ import annotations

import asyncio
import re
import time
from datetime import date, datetime
from typing import Any

from core.observability.logger import get_logger
from .base import DataProvider

_sov = get_logger("adapters.screener_in")
logger = _sov.logger

# ── Cloudflare-aware HTTP session ─────────────────────────────────────────────
try:
    import curl_cffi.requests as _cffi_requests
    _CURL_AVAILABLE = True
except ImportError:
    _cffi_requests = None          # type: ignore[assignment]
    _CURL_AVAILABLE = False
    logger.warning("curl_cffi not installed — ScreenerInProvider will not be available")

# ── HTML parsing ──────────────────────────────────────────────────────────────
try:
    from bs4 import BeautifulSoup, Tag
    _BS4_AVAILABLE = True
except ImportError:
    BeautifulSoup = None           # type: ignore[misc, assignment]
    Tag = None                     # type: ignore[misc, assignment]
    _BS4_AVAILABLE = False
    logger.warning("beautifulsoup4 not installed — ScreenerInProvider will not be available")

# ── Constants ─────────────────────────────────────────────────────────────────
import os

SCREENER_BASE_URL   = os.getenv("SCREENER_BASE_URL",    "https://www.screener.in")
SCREENER_MIN_DELAY  = float(os.getenv("SCREENER_MIN_DELAY_S", "2.0"))   # seconds between requests
SCREENER_TIMEOUT    = float(os.getenv("SCREENER_TIMEOUT_S",   "12.0"))  # per-request timeout
SCREENER_STATEMENT  = os.getenv("SCREENER_STATEMENT",   "consolidated") # or "standalone"
SCREENER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Global rate-limiter shared across all instances (one process = one rate limiter)
_last_request_time: float = 0.0


# ── Helper: parse Indian number formats ──────────────────────────────────────

def _parse_indian_number(text: str | None) -> float | None:
    """Parse numbers formatted with Indian units (Cr, L, %, commas).

    Screener.in uses commas and sometimes 'Cr' (crore) or 'L' (lakh).
    Returns a float or None if parsing fails.

    Examples:
        "1,234.56"  → 1234.56
        "45.32%"    → 45.32
        "12,345 Cr" → 12345.0
        "--"        → None
        ""          → None
    """
    if not text:
        return None
    text = str(text).strip()
    if text in ("--", "-", "N/A", "NA", "", "nan"):
        return None
    # Remove commas, currency symbols, unit suffixes
    text = re.sub(r"[,₹\s]", "", text)
    text = re.sub(r"\s*(Cr|L|lakh|crore|%)\s*$", "", text, flags=re.IGNORECASE)
    try:
        return float(text)
    except ValueError:
        return None


def _parse_percent(text: str | None) -> float | None:
    """Parse percentage text, returning the numeric value (e.g. '15.2%' → 15.2)."""
    if not text:
        return None
    return _parse_indian_number(str(text).replace("%", ""))


def _parse_date(text: str | None) -> str | None:
    """Parse a Screener.in date string to ISO format YYYY-MM-DD.

    Screener uses formats like "Sep 2024", "Q2 FY25", "30 Sep 2024".
    Returns ISO string or None.
    """
    if not text:
        return None
    text = str(text).strip()

    # Try "30 Sep 2024" or "Sep 30, 2024"
    for fmt in ("%d %b %Y", "%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass

    # "Sep 2024" → last day of month
    try:
        dt = datetime.strptime(text, "%b %Y")
        import calendar
        last_day = calendar.monthrange(dt.year, dt.month)[1]
        return date(dt.year, dt.month, last_day).isoformat()
    except ValueError:
        pass

    # "Q2 FY25" → approximate quarter-end date
    # Indian FY: Q1=Apr-Jun, Q2=Jul-Sep, Q3=Oct-Dec, Q4=Jan-Mar
    # FY25 = Apr 2024 – Mar 2025, so Q2 FY25 = Sep 30, 2024
    m = re.match(r"Q(\d)\s*FY(\d{2})", text, re.IGNORECASE)
    if m:
        q, fy_short = int(m.group(1)), int(m.group(2))
        fy = 2000 + fy_short if fy_short < 50 else 1900 + fy_short
        # Calendar year of the quarter end:
        # Q1 (Apr-Jun): cal year = fy-1
        # Q2 (Jul-Sep): cal year = fy-1
        # Q3 (Oct-Dec): cal year = fy-1
        # Q4 (Jan-Mar): cal year = fy
        quarter_map = {
            1: (fy - 1, 6,  30),
            2: (fy - 1, 9,  30),
            3: (fy - 1, 12, 31),
            4: (fy,     3,  31),
        }
        cal_year, month, day = quarter_map.get(q, (fy, 3, 31))
        return date(cal_year, month, day).isoformat()

    return None


# ── Screener.in HTML parser ───────────────────────────────────────────────────

class ScreenerParser:
    """Parses Screener.in company HTML pages.

    Extracts:
      - Top ratios (PE, Book Value, ROCE, ROE, Dividend Yield, Market Cap)
      - 5Y/10Y CAGR from P&L table
      - CFO/PAT ratio from Cash Flow + P&L
      - Quarterly result dates (for PIT pub_date)
      - Promoter holding from Shareholding table
      - Sector from About section
    """

    def __init__(self, html: str, symbol: str):
        self.soup = BeautifulSoup(html, "lxml")
        self.symbol = symbol

    # ── Top ratios ────────────────────────────────────────────────────────────

    def _get_top_ratios(self) -> dict[str, float | None]:
        """Parse the #top-ratios list — the main KPI section on every page."""
        ratios: dict[str, float | None] = {}
        section = self.soup.find("ul", {"id": "top-ratios"})
        if not isinstance(section, Tag):
            return ratios
        for li in section.find_all("li"):
            if not isinstance(li, Tag):
                continue
            # Structure: <li><span class="name">Market Cap</span><span class="value">...</span></li>
            name_el = li.find("span", class_=re.compile(r"name"))
            val_el  = li.find("span", class_=re.compile(r"(value|number)"))
            if not name_el or not val_el:
                continue
            name = name_el.get_text(strip=True).lower()
            val_text = val_el.get_text(strip=True)
            parsed = _parse_indian_number(val_text)

            if "market cap" in name:
                ratios["Market_Cap_Cr"] = parsed
            elif "current price" in name:
                ratios["Price"] = parsed
            elif "stock p/e" in name:
                ratios["PE_Ratio"] = parsed
            elif "book value" in name:
                ratios["Book_Value"] = parsed
            elif "dividend yield" in name:
                ratios["Dividend_Yield%"] = parsed
            elif "roce" in name:
                ratios["ROCE%"] = parsed
            elif "roe" in name:
                ratios["ROE%"] = parsed
            elif "face value" in name:
                ratios["Face_Value"] = parsed
            elif "52 week high" in name or "high / low" in name:
                # "High / Low" is often a combined field — split on "/"
                if "/" in val_text:
                    parts = val_text.split("/")
                    ratios["52W_High"] = _parse_indian_number(parts[0].strip())
                    ratios["52W_Low"]  = _parse_indian_number(parts[1].strip())
                else:
                    ratios["52W_High"] = parsed
            elif "52 week low" in name:
                ratios["52W_Low"] = parsed

        return ratios

    # ── P&L table: 5Y and 10Y CAGR ───────────────────────────────────────────

    def _get_pnl_data(self) -> dict[str, float | None]:
        """Parse the P&L table for compounded growth rows.

        Screener shows CAGR rows at the bottom of the P&L section:
          "Compounded Sales Growth" and "Compounded Profit Growth"
        with columns: 10 Years, 5 Years, 3 Years, TTM.
        """
        result: dict[str, float | None] = {}
        section = self.soup.find("section", {"id": "profit-loss"})
        if not isinstance(section, Tag):
            return result

        for row in section.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()

            # "Compounded Sales Growth" row
            if "compounded sales growth" in label or "sales growth" in label:
                # Columns: [label, 10Y, 5Y, 3Y, TTM]
                if len(cells) >= 3:
                    result["Sales_Growth_10Y%"] = _parse_percent(cells[1].get_text(strip=True))
                    result["Sales_Growth_5Y%"]  = _parse_percent(cells[2].get_text(strip=True))
                if len(cells) >= 4:
                    result["Sales_Growth_3Y%"]  = _parse_percent(cells[3].get_text(strip=True))

            # "Compounded Profit Growth" row
            elif "compounded profit growth" in label or "profit growth" in label:
                if len(cells) >= 3:
                    result["EPS_Growth_10Y%"] = _parse_percent(cells[1].get_text(strip=True))
                    result["EPS_Growth%"]     = _parse_percent(cells[2].get_text(strip=True))
                if len(cells) >= 4:
                    result["EPS_Growth_3Y%"] = _parse_percent(cells[3].get_text(strip=True))

            # "Return on Equity" row in P&L (multi-year ROE)
            elif "return on equity" in label:
                if len(cells) >= 3:
                    result["Avg_ROE_5Y%"] = _parse_percent(cells[2].get_text(strip=True))

        return result

    # ── Cash Flow table: CFO ─────────────────────────────────────────────────

    def _get_cashflow_data(self) -> dict[str, float | None]:
        """Extract CFO values from the Cash Flow table (last 3 years)."""
        result: dict[str, float | None] = {}
        section = self.soup.find("section", {"id": "cash-flow"})
        if not isinstance(section, Tag):
            return result

        cfo_values: list[float] = []
        pat_values: list[float] = []

        for row in section.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()
            if "cash from operating" in label or "operating activities" in label:
                # Take the last 3 columns (most recent years)
                for cell in cells[-3:]:
                    v = _parse_indian_number(cell.get_text(strip=True))
                    if v is not None:
                        cfo_values.append(v)

        # PAT comes from P&L section
        pnl_section = self.soup.find("section", {"id": "profit-loss"})
        if isinstance(pnl_section, Tag):
            for row in pnl_section.find_all("tr"):
                if not isinstance(row, Tag):
                    continue
                cells = row.find_all("td")
                if not cells:
                    continue
                label = cells[0].get_text(strip=True).lower()
                if label in ("net profit", "profit after tax", "pat"):
                    for cell in cells[-3:]:
                        v = _parse_indian_number(cell.get_text(strip=True))
                        if v is not None:
                            pat_values.append(v)
                    break

        if cfo_values and pat_values and len(pat_values) >= 1:
            # Use trailing 3-year averages where available
            avg_cfo = sum(cfo_values[-3:]) / len(cfo_values[-3:])
            avg_pat = sum(pat_values[-3:]) / len(pat_values[-3:])
            if avg_pat and avg_pat != 0:
                result["CFO_PAT_Ratio"] = round(avg_cfo / avg_pat, 3)

        return result

    # ── Quarterly results: pub_date for PIT ──────────────────────────────────

    def _get_quarterly_dates(self) -> dict[str, str | None]:
        """Extract the most recent quarterly result announcement date.

        Screener shows a "Result Date" column in the quarterly results table.
        This is the actual announcement date — what PIT enforcement needs.

        Returns:
            {
                "Quarter_End":  "2024-09-30",   # end of the quarter
                "As_Of_Date":   "2024-10-30",   # date results were announced
            }
        """
        result: dict[str, str | None] = {
            "Quarter_End": None,
            "As_Of_Date": None,
        }
        section = self.soup.find("section", {"id": "quarters"})
        if not isinstance(section, Tag):
            return result

        table = section.find("table")
        if not isinstance(table, Tag):
            return result

        # Header row: find which column is "Sep 2024" style (quarter) and "Result Date"
        header = table.find("thead")
        if not isinstance(header, Tag):
            return result

        header_cells = [th.get_text(strip=True) for th in header.find_all("th")]
        # Most recent quarter is usually the last column in the header
        # Header example: ["", "Sep 2022", "Dec 2022", ..., "Sep 2024"]
        # Find "Result Date" row in tbody
        tbody = table.find("tbody")
        if not isinstance(tbody, Tag):
            return result

        latest_quarter: str | None = None
        latest_result_date: str | None = None

        for row in tbody.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all("td")
            if not cells:
                continue
            label = cells[0].get_text(strip=True).lower()

            if "result date" in label or "ann" in label:
                # The result dates row — most recent is the last column
                date_cells = [c.get_text(strip=True) for c in cells[1:] if c.get_text(strip=True)]
                if date_cells:
                    latest_result_date = _parse_date(date_cells[-1])

        # The most recent quarter comes from the last header column
        if len(header_cells) >= 2:
            for h in reversed(header_cells[1:]):
                if h and h not in ("", "TTM", "YoY"):
                    latest_quarter = _parse_date(h)
                    break

        result["Quarter_End"] = latest_quarter
        result["As_Of_Date"]  = latest_result_date or latest_quarter

        return result

    # ── Shareholding: promoter holding ───────────────────────────────────────

    def _get_shareholding(self) -> dict[str, float | None]:
        """Extract promoter and institutional holding from shareholding section."""
        result: dict[str, float | None] = {}
        section = self.soup.find("section", {"id": "shareholding"})
        if not isinstance(section, Tag):
            return result

        for row in section.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            # Most recent value = last cell
            latest_val = cells[-1].get_text(strip=True)

            if "promoter" in label and "pledge" not in label:
                result["Promoter_Holding%"] = _parse_percent(latest_val)
            elif "fii" in label or "foreign" in label:
                result["FII_Holding%"] = _parse_percent(latest_val)
            elif "dii" in label or "domestic inst" in label:
                result["DII_Holding%"] = _parse_percent(latest_val)
            elif "public" in label and "institution" not in label:
                result["Public_Holding%"] = _parse_percent(latest_val)

        # Institutional = FII + DII
        fii = result.get("FII_Holding%")
        dii = result.get("DII_Holding%")
        if fii is not None and dii is not None:
            result["Inst_Holding%"] = round(fii + dii, 2)

        return result

    # ── Promoter pledge ───────────────────────────────────────────────────────

    def _get_pledge(self) -> float | None:
        """Extract latest promoter pledge % from the shareholding section."""
        section = self.soup.find("section", {"id": "shareholding"})
        if not isinstance(section, Tag):
            return None
        for row in section.find_all("tr"):
            if not isinstance(row, Tag):
                continue
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True).lower()
            if "pledge" in label:
                return _parse_percent(cells[-1].get_text(strip=True))
        return None

    # ── Sector ────────────────────────────────────────────────────────────────

    def _get_sector(self) -> str | None:
        """Extract sector from the About section or company metadata."""
        # Screener shows sector in the company description area
        about = self.soup.find("div", class_=re.compile(r"company-info|about|description"))
        if isinstance(about, Tag):
            for a in about.find_all("a", href=True):
                if not isinstance(a, Tag):
                    continue
                href = a["href"]
                if "/screen/sector/" in href or "/sector/" in href:
                    return str(a.get_text(strip=True))

        # Fallback: look for sector in any metadata list
        for tag in self.soup.find_all(["span", "div"], class_=re.compile(r"sector|industry")):
            text = tag.get_text(strip=True)
            if text and len(text) > 2:
                return str(text)

        return None

    # ── Piotroski F-Score ─────────────────────────────────────────────────────

    def _compute_f_score(self) -> int | None:
        """Compute a simplified Piotroski F-Score from available balance sheet data.

        Full Piotroski requires 9 signals across profitability, leverage, and
        efficiency. We compute what's available from Screener's public tables.
        Returns a score 0–9 or None if insufficient data.
        """
        score = 0
        signals_computed = 0

        roe = self._get_top_ratios().get("ROE%")
        if roe is not None:
            signals_computed += 1
            if roe > 0:
                score += 1   # positive ROA proxy

        cfo_data = self._get_cashflow_data()
        cfo_pat = cfo_data.get("CFO_PAT_Ratio")
        if cfo_pat is not None:
            signals_computed += 1
            if cfo_pat > 1.0:
                score += 1   # CFO > net income (quality earnings)

        return score if signals_computed >= 2 else None

    # ── Master parse ─────────────────────────────────────────────────────────

    def parse(self) -> dict[str, Any]:
        """Run all parsers and assemble the canonical output dict."""
        top    = self._get_top_ratios()
        pnl    = self._get_pnl_data()
        cf     = self._get_cashflow_data()
        dates  = self._get_quarterly_dates()
        sh     = self._get_shareholding()
        sector = self._get_sector()
        pledge = self._get_pledge()
        fscore = self._compute_f_score()

        # Derive Avg_ROE_5Y% from P&L if not already computed
        avg_roe = pnl.pop("Avg_ROE_5Y%", None) or top.get("ROE%")

        return {
            # ── Identity
            "Symbol":            self.symbol,
            "source":            "screener_in",

            # ── Valuation
            "PE_Ratio":          top.get("PE_Ratio"),
            "Book_Value":        top.get("Book_Value"),
            "Market_Cap_Cr":     top.get("Market_Cap_Cr"),
            "Price":             top.get("Price"),
            "Dividend_Yield%":   top.get("Dividend_Yield%"),
            "Face_Value":        top.get("Face_Value"),
            "52W_High":          top.get("52W_High"),
            "52W_Low":           top.get("52W_Low"),

            # ── Quality / profitability
            "ROE%":              top.get("ROE%"),
            "ROCE%":             top.get("ROCE%"),
            "Avg_ROE_5Y%":       avg_roe,
            "CFO_PAT_Ratio":     cf.get("CFO_PAT_Ratio"),

            # ── Growth (what Screener uniquely provides vs yFinance)
            "Sales_Growth_5Y%":  pnl.get("Sales_Growth_5Y%"),
            "Sales_Growth_3Y%":  pnl.get("Sales_Growth_3Y%"),
            "Sales_Growth_10Y%": pnl.get("Sales_Growth_10Y%"),
            "EPS_Growth%":       pnl.get("EPS_Growth%"),
            "EPS_Growth_3Y%":    pnl.get("EPS_Growth_3Y%"),
            "EPS_Growth_10Y%":   pnl.get("EPS_Growth_10Y%"),

            # ── Capital structure
            "Promoter_Holding%": sh.get("Promoter_Holding%"),
            "FII_Holding%":      sh.get("FII_Holding%"),
            "DII_Holding%":      sh.get("DII_Holding%"),
            "Inst_Holding%":     sh.get("Inst_Holding%"),
            "pledge_percent":    pledge or 0,

            # ── PIT dates (critical for enforce_pit_gate)
            "Quarter_End":       dates.get("Quarter_End"),
            "As_Of_Date":        dates.get("As_Of_Date"),

            # ── Classification
            "Sector":            sector,

            # ── Quality score
            "F_Score":           fscore,
        }


# ── ScreenerInProvider ────────────────────────────────────────────────────────

class ScreenerInProvider(DataProvider):
    """Screener.in free data provider.

    Priority: insert at index 1 in data_service.py (after PNSEAProvider,
    before NSEPythonProvider). It is the best free source for 5Y/10Y CAGR,
    ROCE, CFO/PAT, and quarterly announcement dates.

    The provider is automatically disabled when curl_cffi or beautifulsoup4
    is not installed — a warning is logged but no exception is raised.
    """

    @property
    def name(self) -> str:
        return "screener_in"

    def __init__(self, executor=None):
        super().__init__()
        self.executor = executor
        if not _CURL_AVAILABLE or not _BS4_AVAILABLE:
            self.available = False
            logger.warning(
                "ScreenerInProvider disabled — install curl_cffi and beautifulsoup4: "
                "pip install curl_cffi beautifulsoup4 lxml"
            )

    def _symbol_to_url(self, symbol: str) -> str:
        """Convert NSE symbol to Screener.in URL.

        Handles common suffix patterns:
          RELIANCE.NS   → https://www.screener.in/company/RELIANCE/consolidated/
          RELIANCE      → https://www.screener.in/company/RELIANCE/consolidated/
          HDFCBANK      → https://www.screener.in/company/HDFCBANK/consolidated/
        """
        # Strip exchange suffixes (.NS, .BO, .BSE)
        clean = re.sub(r"\.(NS|BO|BSE)$", "", symbol.strip().upper())
        return f"{SCREENER_BASE_URL}/company/{clean}/{SCREENER_STATEMENT}/"

    def _rate_limit(self) -> None:
        """Enforce minimum delay between requests (module-level shared state)."""
        global _last_request_time
        elapsed = time.monotonic() - _last_request_time
        if elapsed < SCREENER_MIN_DELAY:
            time.sleep(SCREENER_MIN_DELAY - elapsed)
        _last_request_time = time.monotonic()

    def _fetch_html(self, url: str) -> str | None:
        """Fetch Screener.in HTML using curl_cffi to bypass Cloudflare.

        Returns raw HTML string or None on failure.
        """
        self._rate_limit()
        try:
            resp = _cffi_requests.get(
                url,
                impersonate="chrome110",
                headers={
                    "User-Agent":      SCREENER_USER_AGENT,
                    "Accept":          "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Referer":         SCREENER_BASE_URL + "/",
                    "DNT":             "1",
                },
                timeout=SCREENER_TIMEOUT,
                allow_redirects=True,
            )
            if resp.status_code == 200:
                return resp.text
            if resp.status_code == 404:
                logger.info("screener_not_found", url=url)
                return None
            logger.warning(
                "screener_http_error",
                status=resp.status_code,
                url=url,
            )
            return None
        except Exception as exc:
            logger.warning("screener_request_failed", url=url, error=str(exc))
            return None

    def _try_standalone_fallback(self, symbol: str) -> str | None:
        """If consolidated page fails, try standalone."""
        clean = re.sub(r"\.(NS|BO|BSE)$", "", symbol.strip().upper())
        url = f"{SCREENER_BASE_URL}/company/{clean}/standalone/"
        return self._fetch_html(url)

    async def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        """Fetch and parse Screener.in data for a given NSE symbol.

        Returns the canonical data dict or raises on failure.
        The data_service.py safe_fetch wrapper catches all exceptions.
        """
        if not self.available:
            raise RuntimeError("ScreenerInProvider not available — missing dependencies")

        loop = asyncio.get_running_loop()
        url  = self._symbol_to_url(symbol)

        # Fetch in executor (blocking I/O, avoids blocking the event loop)
        html = await loop.run_in_executor(self.executor, self._fetch_html, url)

        # Fallback to standalone if consolidated not available
        if html is None:
            html = await loop.run_in_executor(
                self.executor,
                self._try_standalone_fallback,
                symbol,
            )

        if html is None:
            raise ValueError(f"ScreenerIn: no data for {symbol}")

        # Minimal health check — Screener pages always have #top-ratios
        if "top-ratios" not in html and "company-name" not in html:
            raise ValueError(f"ScreenerIn: unexpected page content for {symbol}")

        parser = ScreenerParser(html, symbol)
        return parser.parse()
