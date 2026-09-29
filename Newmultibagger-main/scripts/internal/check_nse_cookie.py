#!/usr/bin/env python3
"""Utility script to verify and test NSE_COOKIE for NSEXBRLProvider.

Usage:
    python scripts/internal/check_nse_cookie.py [SYMBOL]
"""

import os
import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv

# Explicitly load .env from project root
env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(dotenv_path=env_path)


def test_cookie(test_symbol: str = "INFY.NS") -> bool:
    cookie = os.environ.get("NSE_COOKIE", "").strip()
    print("=" * 60)
    print("NSE Cookie & NSEXBRLProvider Diagnostic Tool")
    print("=" * 60)

    if not cookie:
        print("[!] NSE_COOKIE is NOT set in .env or environment.")
        print("\nHow to get a fresh cookie:")
        print("  1. Open https://www.nseindia.com in Chrome or Edge")
        print("  2. Open Developer Tools (F12) -> Network tab")
        print("  3. Refresh the page (Ctrl+R)")
        print("  4. Click on any request to nseindia.com (e.g. quote-equity)")
        print("  5. In 'Request Headers', copy the value of 'Cookie:'")
        print("  6. Paste it into .env as: NSE_COOKIE=\"<copied_cookie>\"\n")
        return False

    print(f"[+] Found NSE_COOKIE (length: {len(cookie)} chars)")
    print(f"[*] Initializing NSEXBRLProvider and testing with {test_symbol}...")

    try:
        from modules.adapters.nse_xbrl_provider import NSEXBRLProvider

        provider = NSEXBRLProvider()
        if not provider.available:
            print("[-] NSEXBRLProvider initialized but marked unavailable.")
            return False

        print("[+] NSEXBRLProvider is enabled and available.")
        print(f"[*] Fetching XBRL fundamentals for {test_symbol}...")
        data = provider._fetch_sync(test_symbol)

        print("\n" + "-" * 40)
        print(f"[SUCCESS] NSE XBRL Data for {test_symbol}:")
        print("-" * 40)
        print(f"  Source        : {data.get('source')}")
        print(f"  ROE%          : {data.get('ROE%')}%")
        print(f"  Debt/Equity   : {data.get('Debt_Equity')}")
        print(f"  Book Value    : {data.get('Book_Value')}")
        print(f"  Sales Growth  : {data.get('Sales_Growth_TTM%')}% (TTM)")
        print(f"  EPS Growth    : {data.get('EPS_Growth%')}% (TTM)")
        print(f"  Quarter End   : {data.get('Quarter_End')}")
        print(f"  As Of Date    : {data.get('As_Of_Date')}")
        print(f"  Consolidated  : {data.get('filing_consolidated')}")
        print("=" * 60)
        return True
    except Exception as e:
        print(f"\n[-] Error fetching data with NSE_COOKIE: {e}")
        print("[-] The cookie may be expired (NSE cookies typically last a few hours).")
        print("[-] Please copy a fresh cookie from your browser.")
        return False


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "INFY.NS"
    success = test_cookie(symbol)
    sys.exit(0 if success else 1)
