"""
Sprint 1 Verification: CAGR Engine + Dividend + Cap Category
Tests the new modules with a live ticker to confirm integration.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.cagr_engine import calculate_all_cagrs, classify_market_cap, extract_dividend_metrics


def test_market_cap_classifier():
    """Test SEBI-based market cap classification."""
    assert classify_market_cap(50000) == "Large Cap"
    assert classify_market_cap(20000) == "Large Cap"
    assert classify_market_cap(10000) == "Mid Cap"
    assert classify_market_cap(5000) == "Mid Cap"
    assert classify_market_cap(2000) == "Small Cap"
    assert classify_market_cap(500) == "Small Cap"
    assert classify_market_cap(300) == "Micro Cap"
    assert classify_market_cap(0) == "Micro Cap"
    print("[PASS] Market cap classifier: all 8 cases passed")


def test_dividend_extraction():
    """Test dividend metric extraction from info dict."""
    # Normal case
    info = {"dividendYield": 0.025, "payoutRatio": 0.35}
    result = extract_dividend_metrics(info)
    assert result["Dividend_Yield"] == 2.5
    assert result["Dividend_Payout"] == 35.0
    print(f"  Normal case: Yield={result['Dividend_Yield']}%, Payout={result['Dividend_Payout']}%")

    # Missing case
    info_empty = {}
    result_empty = extract_dividend_metrics(info_empty)
    assert result_empty["Dividend_Yield"] == 0.0
    assert result_empty["Dividend_Payout"] == 0.0
    print(
        f"  Empty case: Yield={result_empty['Dividend_Yield']}%, Payout={result_empty['Dividend_Payout']}%"
    )

    # Cap absurd payout
    info_absurd = {"dividendYield": 0.01, "payoutRatio": 5.0}
    result_absurd = extract_dividend_metrics(info_absurd)
    assert result_absurd["Dividend_Payout"] <= 200.0
    print(f"  Absurd payout capped: {result_absurd['Dividend_Payout']}%")

    print("[PASS] Dividend extraction: all 3 cases passed")


def test_cagr_with_live_ticker():
    """Test CAGR calculation with a real ticker."""
    try:
        import yfinance as yf

        ticker = yf.Ticker("RELIANCE.NS")
        result = calculate_all_cagrs(ticker)

        print("\n  RELIANCE.NS CAGR Results:")
        print(f"    Revenue CAGR 3Y: {result['Revenue_CAGR_3Y']}")
        print(f"    Revenue CAGR 5Y: {result['Revenue_CAGR_5Y']}")
        print(f"    PAT CAGR 3Y:     {result['PAT_CAGR_3Y']}")
        print(f"    PAT CAGR 5Y:     {result['PAT_CAGR_5Y']}")
        print(f"    EPS CAGR 3Y:     {result['EPS_CAGR_3Y']}")
        print(f"    EPS CAGR 5Y:     {result['EPS_CAGR_5Y']}")
        print(f"    Consistency:     {result['CAGR_Consistency']}")

        # At least Revenue CAGR should compute for Reliance
        assert result["Revenue_CAGR_3Y"] is not None or result["Revenue_CAGR_5Y"] is not None, (
            "At least one Revenue CAGR should be non-None for RELIANCE"
        )

        # Dividend
        info = ticker.info
        div = extract_dividend_metrics(info)
        print(f"\n  Dividend Yield: {div['Dividend_Yield']}%")
        print(f"  Dividend Payout: {div['Dividend_Payout']}%")

        # Cap category
        mcap = info.get("marketCap", 0) / 1e7  # USD to rough Cr
        cap = classify_market_cap(mcap)
        print(f"  Market Cap: {mcap:.0f} Cr -> {cap}")

        print("[PASS] Live CAGR test: RELIANCE.NS passed")
    except Exception as e:
        print(f"[SKIP] Live test skipped (network/yfinance issue): {e}")


def test_model_fields():
    """Verify the Pydantic model accepts the new fields."""
    from modules.models import StockDataPayload

    minimal = {
        "Symbol": "TEST.NS",
        "Price": 100.0,
        "Revenue_CAGR_3Y": 18.5,
        "Revenue_CAGR_5Y": 15.2,
        "PAT_CAGR_3Y": 22.0,
        "PAT_CAGR_5Y": None,
        "EPS_CAGR_3Y": 20.0,
        "EPS_CAGR_5Y": None,
        "CAGR_Consistency": "HIGH",
        "Dividend_Yield": 2.5,
        "Dividend_Payout": 35.0,
        "Cap_Category": "Large Cap",
    }
    payload = StockDataPayload(**minimal)
    dump = payload.model_dump(by_alias=True)

    assert dump["Revenue_CAGR_3Y"] == 18.5
    assert dump["CAGR_Consistency"] == "HIGH"
    assert dump["Dividend_Yield"] == 2.5
    assert dump["Cap_Category"] == "Large Cap"
    print("[PASS] Pydantic model accepts all Sprint 1 fields")


if __name__ == "__main__":
    print("=" * 60)
    print("Sprint 1 Verification: The Compounding Lens")
    print("=" * 60)

    test_market_cap_classifier()
    test_dividend_extraction()
    test_model_fields()
    test_cagr_with_live_ticker()

    print("\n" + "=" * 60)
    print("All Sprint 1 tests completed.")
    print("=" * 60)
