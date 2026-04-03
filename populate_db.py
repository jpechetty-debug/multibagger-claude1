"""Quick population script — fetches a few tickers via yfinance and inserts into multibaggers."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yfinance as yf
import sqlite3
import numpy as np
from datetime import datetime
from modules.scoring import calculate_institutional_score
from modules.fundamentals import calculate_piotroski_f_score

TICKERS = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "HINDUNILVR.NS", "BHARTIARTL.NS", "BAJFINANCE.NS", "SBIN.NS", "LT.NS",
    "ITC.NS", "KOTAKBANK.NS", "AXISBANK.NS", "MARUTI.NS", "TITAN.NS"
]

def populate():
    conn = sqlite3.connect("stocks.db")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    inserted = 0
    for symbol in TICKERS:
        try:
            print(f"  Fetching {symbol}...", end="\r")
            t = yf.Ticker(symbol)
            info = t.info
            if not info or not info.get("currentPrice"):
                print(f"  Skipped {symbol} (no price data)")
                continue

            hist = t.history(period="1y")
            if hist.empty:
                continue

            price = info.get("currentPrice", 0)
            roe = (info.get("returnOnEquity") or 0) * 100
            de = (info.get("debtToEquity") or 0) / 100
            sales_g = (info.get("revenueGrowth") or 0) * 100
            eps_g = (info.get("earningsGrowth") or 0) * 100
            pe = info.get("trailingPE") or 0
            mcap = (info.get("marketCap") or 0) / 1e7
            sector = info.get("sector", "Unknown")
            name = info.get("shortName", symbol)
            prom = (info.get("heldPercentInsiders") or 0) * 100
            cfo = info.get("operatingCashflow") or 0
            pat = info.get("netIncomeToCommon") or 1
            cfo_pat = round(cfo / pat, 2) if pat > 0 else 0

            # RS Rating
            rs = 0
            if len(hist) > 126:
                p6m = hist["Close"].iloc[-126]
                rs = round(((price - p6m) / p6m) * 100, 2) if p6m > 0 else 0

            # 52W
            high_52w = info.get("fiftyTwoWeekHigh", price)
            low_52w = info.get("fiftyTwoWeekLow", price)
            down_52w = round(((high_52w - price) / high_52w) * 100, 2) if high_52w > 0 else 0

            # F-Score
            try:
                f_score = calculate_piotroski_f_score(t)
            except Exception:
                f_score = 5

            # Score
            data = {
                "ROE%": roe, "Sales_Growth_TTM%": sales_g, "Debt_Equity": de,
                "F_Score": f_score, "PE_Ratio": pe, "Market_Cap_Cr": mcap,
                "Down_From_52W_High%": down_52w, "CFO_PAT_Ratio": cfo_pat,
                "EPS_Growth%": eps_g, "RS_Rating": rs,
            }
            score_res = calculate_institutional_score(data, market_regime="SIDEWAYS")
            score = score_res["total_score"]

            cursor.execute("""
                INSERT OR REPLACE INTO multibaggers
                (symbol, name, price, score, sector, pe_ratio, market_cap_cr,
                 roe_pct, debt_equity, sales_cagr_5y, eps_growth, cfo_pat_ratio,
                 f_score, rs_rating, promoter_holding, high_52w, low_52w,
                 down_from_52w_high, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (symbol, name, price, score, sector, pe, mcap, roe, de,
                  sales_g, eps_g, cfo_pat, f_score, rs, prom, high_52w,
                  low_52w, down_52w, datetime.now().isoformat()))
            inserted += 1
            print(f"  ✅ {symbol}: Score={score:.1f}, Price={price:.2f}")

        except Exception as e:
            print(f"  ❌ {symbol}: {e}")
            continue

    conn.commit()
    conn.close()
    print(f"\n{'='*50}")
    print(f"  Populated {inserted}/{len(TICKERS)} stocks into multibaggers")
    print(f"{'='*50}")

if __name__ == "__main__":
    populate()
