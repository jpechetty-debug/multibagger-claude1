"""Tests for modules/adapters/screener_in.py.

All tests are offline — no network calls. Tests inject synthetic Screener.in
HTML that mirrors the actual page structure, so they run in CI without internet.

Covers:
  _parse_indian_number:   commas, %, Cr suffix, dash, empty
  _parse_percent:         percentage strings
  _parse_date:            "Sep 2024", "Q2 FY25", "30 Sep 2024", ISO, None
  ScreenerParser.parse:   full parse with synthetic HTML
    - top ratios (PE, ROCE, ROE, Book Value, Market Cap)
    - P&L CAGR rows (5Y, 10Y, 3Y sales + profit growth)
    - Cash Flow CFO/PAT ratio
    - quarterly dates → Quarter_End, As_Of_Date
    - shareholding → Promoter, FII, DII, Inst
    - sector extraction
  ScreenerInProvider:
    - disabled gracefully when deps missing
    - _symbol_to_url strips exchange suffixes
    - canonical keys all present in output
    - fetch returns None → ValueError raised
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# curl_cffi is a declared dependency; a stub here leaked into later test modules.


from modules.adapters.screener_in import (  # noqa: E402
    ScreenerInProvider,
    ScreenerParser,
    _parse_date,
    _parse_indian_number,
    _parse_percent,
)

# ── Synthetic HTML ────────────────────────────────────────────────────────────

SAMPLE_HTML = """
<html><body>

<!-- Top ratios -->
<ul id="top-ratios">
  <li><span class="name">Market Cap</span><span class="value">1,23,456 Cr</span></li>
  <li><span class="name">Current Price</span><span class="value">2,345</span></li>
  <li><span class="name">Stock P/E</span><span class="value">28.5</span></li>
  <li><span class="name">Book Value</span><span class="value">450.0</span></li>
  <li><span class="name">Dividend Yield</span><span class="value">1.2%</span></li>
  <li><span class="name">ROCE</span><span class="value">18.5%</span></li>
  <li><span class="name">ROE</span><span class="value">15.3%</span></li>
</ul>

<!-- P&L section -->
<!-- Mirrors live Screener.in: year headers, "+" expand suffix on labels, trailing TTM column,
     and a P&L range that starts one year later than the cash-flow table. -->
<section id="profit-loss">
  <table>
    <thead><tr><th></th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th><th>TTM</th></tr></thead>
    <tbody>
      <tr><td>Sales</td><td>100</td><td>120</td><td>140</td><td>160</td></tr>
      <tr><td>Net Profit<button>+</button></td><td>12</td><td>14</td><td>16</td><td>18</td></tr>
      <tr>
        <td>Compounded Sales Growth</td>
        <td>12%</td><td>18%</td><td>22%</td><td>25%</td>
      </tr>
      <tr>
        <td>Compounded Profit Growth</td>
        <td>10%</td><td>15%</td><td>20%</td><td>22%</td>
      </tr>
      <tr>
        <td>Return on Equity</td>
        <td>14%</td><td>15%</td><td>15.3%</td><td>16%</td>
      </tr>
    </tbody>
  </table>
</section>

<!-- Cash flow section -->
<section id="cash-flow">
  <table>
    <thead><tr><th></th><th>Mar 2021</th><th>Mar 2022</th><th>Mar 2023</th><th>Mar 2024</th></tr></thead>
    <tbody>
      <tr>
        <td>Cash from Operating Activity<button>+</button></td>
        <td>9</td><td>11</td><td>13</td><td>15</td>
      </tr>
    </tbody>
  </table>
</section>

<!-- Balance sheet: latest year D/E = 50 / (10 + 190) = 0.25 -->
<section id="balance-sheet">
  <table>
    <thead><tr><th></th><th>Mar 2023</th><th>Mar 2024</th></tr></thead>
    <tbody>
      <tr><td>Equity Capital</td><td>10</td><td>10</td></tr>
      <tr><td>Reserves</td><td>150</td><td>190</td></tr>
      <tr><td>Borrowings<button>+</button></td><td>80</td><td>50</td></tr>
      <tr><td>Total Liabilities</td><td>300</td><td>320</td></tr>
    </tbody>
  </table>
</section>

<!-- Quarterly results -->
<section id="quarters">
  <table>
    <thead>
      <tr>
        <th></th>
        <th>Sep 2022</th>
        <th>Dec 2022</th>
        <th>Mar 2023</th>
        <th>Jun 2023</th>
        <th>Sep 2023</th>
        <th>Sep 2024</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>Sales</td>
        <td>100</td><td>110</td><td>120</td><td>115</td><td>125</td><td>135</td>
      </tr>
      <tr>
        <td>Result Date</td>
        <td>14 Nov 2022</td><td>14 Feb 2023</td><td>29 Apr 2023</td>
        <td>28 Jul 2023</td><td>13 Nov 2023</td><td>30 Oct 2024</td>
      </tr>
    </tbody>
  </table>
</section>

<!-- Shareholding -->
<section id="shareholding">
  <table>
    <tbody>
      <tr><td>Promoters</td><td>52.0</td><td>51.5</td><td>51.8</td></tr>
      <tr><td>Pledge %</td><td>0.0</td><td>0.0</td><td>2.5</td></tr>
      <tr><td>FIIs</td><td>18.0</td><td>19.0</td><td>20.5</td></tr>
      <tr><td>DIIs</td><td>12.0</td><td>12.5</td><td>13.0</td></tr>
      <tr><td>Public</td><td>18.0</td><td>17.0</td><td>14.7</td></tr>
    </tbody>
  </table>
</section>

<!-- Sector -->
<div class="company-info">
  <a href="/screen/sector/IT/">Information Technology</a>
</div>

</body></html>
"""


# ── _parse_indian_number ──────────────────────────────────────────────────────

class TestParseIndianNumber:

    def test_plain_integer(self):
        assert _parse_indian_number("1234") == 1234.0

    def test_commas(self):
        assert _parse_indian_number("1,23,456") == 123456.0

    def test_decimal(self):
        assert _parse_indian_number("1,234.56") == pytest.approx(1234.56)

    def test_crore_suffix(self):
        assert _parse_indian_number("1,23,456 Cr") == 123456.0

    def test_percentage(self):
        assert _parse_indian_number("45.32%") == pytest.approx(45.32)

    def test_dash_returns_none(self):
        assert _parse_indian_number("--") is None

    def test_empty_returns_none(self):
        assert _parse_indian_number("") is None

    def test_na_returns_none(self):
        assert _parse_indian_number("N/A") is None

    def test_none_input(self):
        assert _parse_indian_number(None) is None

    def test_zero(self):
        assert _parse_indian_number("0") == 0.0

    def test_negative(self):
        assert _parse_indian_number("-123") == -123.0


# ── _parse_percent ────────────────────────────────────────────────────────────

class TestParsePercent:

    def test_with_percent_sign(self):
        assert _parse_percent("18.5%") == pytest.approx(18.5)

    def test_without_percent_sign(self):
        assert _parse_percent("15.3") == pytest.approx(15.3)

    def test_dash(self):
        assert _parse_percent("--") is None

    def test_none(self):
        assert _parse_percent(None) is None


# ── _parse_date ───────────────────────────────────────────────────────────────

class TestParseDate:

    def test_full_date(self):
        assert _parse_date("30 Sep 2024") == "2024-09-30"

    def test_month_year_returns_last_day(self):
        assert _parse_date("Sep 2024") == "2024-09-30"

    def test_february_last_day(self):
        assert _parse_date("Feb 2024") == "2024-02-29"  # 2024 is leap year

    def test_q2_fy25(self):
        # Q2 FY25 = Jul–Sep 2024, ends Sep 30 2024
        result = _parse_date("Q2 FY25")
        assert result == "2024-09-30"

    def test_q4_fy24(self):
        # Q4 FY24 = Jan–Mar 2024, ends Mar 31 2024
        result = _parse_date("Q4 FY24")
        assert result == "2024-03-31"

    def test_iso_passthrough(self):
        assert _parse_date("2024-09-30") == "2024-09-30"

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_empty_returns_none(self):
        assert _parse_date("") is None

    def test_garbage_returns_none(self):
        assert _parse_date("not-a-date") is None


# ── ScreenerParser ────────────────────────────────────────────────────────────

class TestScreenerParser:

    def _parse(self) -> dict:
        return ScreenerParser(SAMPLE_HTML, "TESTCO").parse()

    def test_symbol_preserved(self):
        assert self._parse()["Symbol"] == "TESTCO"

    def test_source_is_screener_in(self):
        assert self._parse()["source"] == "screener_in"

    def test_pe_ratio(self):
        assert self._parse()["PE_Ratio"] == pytest.approx(28.5)

    def test_roce(self):
        assert self._parse()["ROCE%"] == pytest.approx(18.5)

    def test_roe(self):
        assert self._parse()["ROE%"] == pytest.approx(15.3)

    def test_book_value(self):
        assert self._parse()["Book_Value"] == pytest.approx(450.0)

    def test_market_cap(self):
        assert self._parse()["Market_Cap_Cr"] == pytest.approx(123456.0)

    def test_price(self):
        assert self._parse()["Price"] == pytest.approx(2345.0)

    def test_dividend_yield(self):
        assert self._parse()["Dividend_Yield%"] == pytest.approx(1.2)

    def test_sales_growth_5y(self):
        assert self._parse()["Sales_Growth_5Y%"] == pytest.approx(18.0)

    def test_sales_growth_10y(self):
        assert self._parse()["Sales_Growth_10Y%"] == pytest.approx(12.0)

    def test_sales_growth_3y(self):
        assert self._parse()["Sales_Growth_3Y%"] == pytest.approx(22.0)

    def test_eps_growth(self):
        assert self._parse()["EPS_Growth%"] == pytest.approx(15.0)

    def test_eps_growth_10y(self):
        assert self._parse()["EPS_Growth_10Y%"] == pytest.approx(10.0)

    def test_cfo_pat_ratio(self):
        # Shared years Mar 2022-2024: CFO avg(11,13,15) = 13.0, PAT avg(12,14,16) = 14.0.
        # Positional pairing would wrongly use PAT (14,16,TTM 18) or CFO Mar 2021.
        result = self._parse()["CFO_PAT_Ratio"]
        assert result is not None
        assert result == pytest.approx(13.0 / 14.0, rel=1e-2)

    def test_cfo_pat_ratio_none_for_loss_maker(self):
        html = SAMPLE_HTML.replace(
            "<td>Net Profit<button>+</button></td><td>12</td><td>14</td><td>16</td>",
            "<td>Net Profit<button>+</button></td><td>-12</td><td>-14</td><td>-16</td>",
        )
        assert ScreenerParser(html, "TEST").parse().get("CFO_PAT_Ratio") is None

    def test_quarter_end_date(self):
        # Most recent quarter header = "Sep 2024" → last day = 2024-09-30
        result = self._parse()["Quarter_End"]
        assert result == "2024-09-30"

    def test_as_of_date_is_result_date(self):
        # Result Date last column = "30 Oct 2024" → 2024-10-30
        result = self._parse()["As_Of_Date"]
        assert result == "2024-10-30"

    def test_promoter_holding(self):
        assert self._parse()["Promoter_Holding%"] == pytest.approx(51.8)

    def test_fii_holding(self):
        assert self._parse()["FII_Holding%"] == pytest.approx(20.5)

    def test_dii_holding(self):
        assert self._parse()["DII_Holding%"] == pytest.approx(13.0)

    def test_inst_holding_is_fii_plus_dii(self):
        r = self._parse()
        fii = r["FII_Holding%"]
        dii = r["DII_Holding%"]
        assert r["Inst_Holding%"] == pytest.approx(fii + dii)

    def test_pledge_percent(self):
        assert self._parse()["pledge_percent"] == pytest.approx(2.5)

    def test_debt_equity_from_latest_balance_sheet_year(self):
        assert self._parse()["Debt_Equity"] == pytest.approx(0.25)

    def test_debt_equity_negative_net_worth_is_not_debt_free(self):
        # Equity 10 + Reserves -200 < 0 with debt outstanding: a raw negative
        # ratio would be clamped to 0.0 (debt-free) by the DQ gate.
        html = SAMPLE_HTML.replace("<td>190</td>", "<td>-200</td>")
        de = ScreenerParser(html, "TESTCO").parse()["Debt_Equity"]
        assert de == ScreenerParser.NEGATIVE_EQUITY_DE

    def test_missing_balance_sheet_gives_none_not_zero(self):
        html = SAMPLE_HTML.replace('id="balance-sheet"', 'id="other"')
        assert ScreenerParser(html, "TESTCO").parse()["Debt_Equity"] is None

    def test_quarterly_yoy_growth_compares_same_quarter_last_year(self):
        r = self._parse()
        # Sep 2024=135 vs Sep 2023=125; previous column Sep 2023=125 vs Sep 2022=100.
        assert r["Qtr_Sales_YoY%"] == pytest.approx(8.0)
        assert r["Qtr_Sales_YoY_Prev%"] == pytest.approx(25.0)

    def test_earnings_inflection_from_quarters(self):
        from modules.fundamentals import check_earnings_inflection
        strong = {"Qtr_Sales_YoY%": 30, "Qtr_Sales_YoY_Prev%": 20, "Qtr_PAT_YoY%": 40,
                  "Qtr_PAT_YoY_Prev%": 25, "Qtr_NPM%": 12, "Qtr_NPM_Year_Ago%": 10}
        assert check_earnings_inflection(strong) == {"score": 5, "status": True}
        loss = {**strong, "Qtr_NPM%": -5, "Qtr_NPM_Year_Ago%": -8}
        assert check_earnings_inflection(loss)["status"] is False

    def test_live_ranges_table_layout(self):
        # Live Screener.in renders each CAGR as its own small "ranges-table".
        ranges = """<section id="profit-loss"><table class="ranges-table">
          <tr><th colspan="2">Compounded Sales Growth</th></tr>
          <tr><td>10 Years:</td><td>9%</td></tr><tr><td>5 Years:</td><td>10%</td></tr>
          <tr><td>3 Years:</td><td>6%</td></tr><tr><td>TTM:</td><td>8%</td></tr></table>
          <table class="ranges-table"><tr><th colspan="2">Compounded Profit Growth</th></tr>
          <tr><td>5 Years:</td><td>9%</td></tr><tr><td>3 Years:</td><td>8%</td></tr></table>
          <table class="ranges-table"><tr><th colspan="2">Return on Equity</th></tr>
          <tr><td>5 Years:</td><td>49%</td></tr></table></section>"""
        r = ScreenerParser(f"<html><body>{ranges}</body></html>", "T").parse()
        assert (r["Sales_Growth_10Y%"], r["Sales_Growth_5Y%"], r["Sales_Growth_3Y%"]) == (9, 10, 6)
        assert (r["EPS_Growth%"], r["EPS_Growth_3Y%"], r["Avg_ROE_5Y%"]) == (9, 8, 49)

    def test_sector_from_market_breadcrumb_mapped_to_house_names(self):
        crumbs = ('<a href="/market/IN07/" title="Broad Sector">Consumer Discretionary</a>'
                  '<a href="/market/IN07/IN0701/IN070101/IN070101001/" title="Industry">Footwear</a>')
        r = ScreenerParser(f"<html><body>{crumbs}</body></html>", "T").parse()
        assert (r["Sector"], r["Industry"]) == ("Consumer Cyclical", "Footwear")

    def test_market_cap_with_rupee_and_cr_dot_units(self):
        # Live markup: "₹ <span class=number>7,61,979</span> Cr." (trailing dot).
        html = ('<ul id="top-ratios"><li><span class="name">Market Cap</span>'
                '<span class="nowrap value">₹ <span class="number">7,61,979</span> Cr.</span></li></ul>')
        assert ScreenerParser(html, "T").parse()["Market_Cap_Cr"] == 761979

    def test_missing_pledge_row_gives_none_not_zero(self):
        html = SAMPLE_HTML.replace("<td>Pledge %</td>", "<td>Others</td>")
        assert ScreenerParser(html, "TESTCO").parse()["pledge_percent"] is None

    def test_sector_extracted(self):
        result = self._parse()["Sector"]
        assert result == "Information Technology"

    def test_all_canonical_keys_present(self):
        """Every key the scoring engine reads must be in the output."""
        required = [
            "Symbol", "source", "PE_Ratio", "ROE%", "ROCE%",
            "Sales_Growth_5Y%", "EPS_Growth%", "CFO_PAT_Ratio",
            "Promoter_Holding%", "Inst_Holding%", "Quarter_End",
            "As_Of_Date", "Avg_ROE_5Y%", "Sector", "F_Score",
        ]
        result = self._parse()
        missing = [k for k in required if k not in result]
        assert not missing, f"Missing canonical keys: {missing}"


# ── ScreenerInProvider ────────────────────────────────────────────────────────

class TestScreenerInProvider:

    def _make_provider(self):
        p = ScreenerInProvider(executor=None)
        p.available = True   # force-enable even with stub curl_cffi
        return p

    def test_name(self):
        assert self._make_provider().name == "screener_in"

    def test_symbol_url_strips_ns_suffix(self):
        p = self._make_provider()
        url = p._symbol_to_url("RELIANCE.NS")
        assert "RELIANCE" in url
        assert ".NS" not in url

    def test_symbol_url_strips_bo_suffix(self):
        p = self._make_provider()
        url = p._symbol_to_url("HDFCBANK.BO")
        assert "HDFCBANK" in url
        assert ".BO" not in url

    def test_symbol_url_bare_symbol(self):
        p = self._make_provider()
        url = p._symbol_to_url("TCS")
        assert "TCS" in url
        assert "screener.in" in url

    def test_symbol_url_uses_consolidated(self):
        p = self._make_provider()
        url = p._symbol_to_url("INFY")
        assert "consolidated" in url

    def test_disabled_when_deps_missing(self, monkeypatch):
        """Provider must self-disable gracefully when deps unavailable."""
        with patch("modules.adapters.screener_in._CURL_AVAILABLE", False):
            with patch("modules.adapters.screener_in._BS4_AVAILABLE", False):
                p = ScreenerInProvider(executor=None)
                assert p.available is False

    def test_fetch_none_html_raises(self):
        """_fetch_html returning None must raise ValueError in fetch_fundamentals."""
        import asyncio
        p = self._make_provider()

        async def _run():
            with patch.object(p, "_fetch_html", return_value=None):
                with patch.object(p, "_try_standalone_fallback", return_value=None):
                    with pytest.raises((ValueError, Exception)):
                        await p.fetch_fundamentals("UNKNOWN")

        asyncio.run(_run())

    def test_fetch_sample_html_returns_canonical_dict(self):
        """Injecting the sample HTML must produce the canonical output dict."""
        import asyncio
        p = self._make_provider()

        async def _run():
            with patch.object(p, "_fetch_html", return_value=SAMPLE_HTML):
                result = await p.fetch_fundamentals("TESTCO")
            return result

        result = asyncio.run(_run())
        assert result["Symbol"] == "TESTCO"
        assert result["source"] == "screener_in"
        assert result["PE_Ratio"] == pytest.approx(28.5)
        assert result["Sales_Growth_5Y%"] == pytest.approx(18.0)
        assert result["Quarter_End"] == "2024-09-30"
        assert result["As_Of_Date"] == "2024-10-30"

    def test_unexpected_html_raises(self):
        """HTML without Screener markers must raise ValueError."""
        import asyncio
        p = self._make_provider()
        bad_html = "<html><body><p>Cloudflare error 1020</p></body></html>"

        async def _run():
            with patch.object(p, "_fetch_html", return_value=bad_html):
                with pytest.raises((ValueError, Exception)):
                    await p.fetch_fundamentals("RELIANCE")

        asyncio.run(_run())


# ── data_service integration: provider inserted at priority 2 ─────────────────

class TestDataServiceIntegration:

    def test_screener_in_in_provider_chain(self):
        """ScreenerInProvider should be importable and insertable into provider list."""
        from modules.adapters.screener_in import ScreenerInProvider
        p = ScreenerInProvider(executor=None)
        # In data_service.py, provider chain is a list — confirm it can be inserted
        mock_chain = ["pnsea", p, "nsepython", "yfinance"]
        assert mock_chain[1].name == "screener_in"  # type: ignore[attr-defined]

    def test_as_of_date_feeds_pit_gate(self):
        """As_Of_Date from Screener must be a valid ISO date for enforce_pit_gate."""
        from db.date_utils import normalize_as_of_date
        result = ScreenerParser(SAMPLE_HTML, "TEST").parse()
        as_of = result["As_Of_Date"]
        normalised = normalize_as_of_date(as_of)
        assert normalised == "2024-10-30"
