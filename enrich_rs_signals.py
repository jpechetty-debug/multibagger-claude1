import yfinance as yf
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime
import sys
import os
import time

# Set up paths for modules
sys.path.append(os.getcwd())
try:
    from modules.scoring import calculate_institutional_score
    from modules.fundamentals import calculate_piotroski_f_score
except ImportError:
    # Fallback to dummy if modules missing (though they should be present)
    def calculate_institutional_score(data, **kwargs): return {"total_score": 50}
    def calculate_piotroski_f_score(t): return 5

def enrich():
    db_path = "stocks.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Fetch symbols that haven't been enriched yet
    cursor.execute("SELECT * FROM multibaggers WHERE last_audited IS NULL")
    stocks = cursor.fetchall()
    
    if not stocks:
        print("No stocks found for enrichment.")
        conn.close()
        return

    print(f"Found {len(stocks)} stocks to enrich. Starting Throttled Forensic Scan (2s delay)...")

    for i, stock in enumerate(stocks):
        symbol = stock['symbol']
        print(f"[{i+1}/{len(stocks)}] Deep Scan: {symbol}...", end="\r")
        
        try:
            # Robust Throttling
            time.sleep(2.0)
            
            t = yf.Ticker(symbol)
            info = t.info
            if not info or not info.get("currentPrice"):
                print(f"  Skipped {symbol} (No price data)")
                continue

            # Core Metrics
            price = info.get("currentPrice") or 0
            name = info.get("shortName") or info.get("longName") or symbol
            sector = info.get("sector") or "Unknown"
            
            # Fundamentals
            roe = (info.get("returnOnEquity") or 0) * 100
            pe = info.get("trailingPE") or info.get("forwardPE") or 0
            mcap_cr = (info.get("marketCap") or 0) / 1e7
            debt_equity = (info.get("debtToEquity") or 0) / 100
            sales_growth = (info.get("revenueGrowth") or 0) * 100
            cfo = info.get("operatingCashflow") or 0
            pat = info.get("netIncomeToCommon") or 1
            cfo_pat = round(cfo / pat, 2) if pat > 0 else 0
            
            # Additional V3.1 Metrics
            try:
                f_score = calculate_piotroski_f_score(t)
            except:
                f_score = 5
                
            # Technicals (approximate for RS)
            hist = t.history(period="1y")
            rs_rating = 0
            if not hist.empty and len(hist) > 126:
                p6m = hist["Close"].iloc[-126]
                rs_rating = round(((price - p6m) / p6m) * 100, 2) if p6m > 0 else 0

            # 52W High/Low
            high_52w = info.get("fiftyTwoWeekHigh", price)
            low_52w = info.get("fiftyTwoWeekLow", price)
            down_52w = round(((high_52w - price) / high_52w) * 100, 2) if high_52w > 0 else 0

            # Scoring Data Payload
            score_data = {
                "ROE%": roe,
                "Sales_Growth_TTM%": sales_growth,
                "Debt_Equity": debt_equity,
                "F_Score": f_score,
                "PE_Ratio": pe,
                "Market_Cap_Cr": mcap_cr,
                "Down_From_52W_High%": down_52w,
                "CFO_PAT_Ratio": cfo_pat,
                "RS_Rating": rs_rating
            }
            
            try:
                score_res = calculate_institutional_score(score_data, market_regime="SIDEWAYS")
                final_score = score_res.get("total_score", 50)
            except:
                final_score = 50
                
            # Update Database record
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            cursor.execute("""
                UPDATE multibaggers 
                SET name = ?,
                    price = ?,
                    sector = ?,
                    score = ?,
                    f_score = ?,
                    sales_growth = ?,
                    roe = ?,
                    debt_equity = ?,
                    market_cap_cr = ?,
                    cfo_pat_ratio = ?,
                    pe_ratio = ?,
                    down_from_52w = ?,
                    rs_rating = ?,
                    high_52w = ?,
                    low_52w = ?,
                    last_audited = ?,
                    updated_at = ?
                WHERE symbol = ?
            """, (
                name, price, sector, final_score, f_score, sales_growth, roe, 
                debt_equity, mcap_cr, cfo_pat, pe, down_52w, rs_rating, 
                high_52w, low_52w, now_str, now_str, symbol
            ))
            
            if (i + 1) % 5 == 0:
                conn.commit()
                print(f"\n[AUDIT] Checkpoint: Commit for {i+1} symbols...")

        except Exception as e:
            print(f"\n[ERROR] Failed to enrich {symbol}: {e}")
            if "429" in str(e):
                print("[SYSTEM] High rate limit detected. Sleeping 60s...")
                time.sleep(60)
            continue

    conn.commit()
    conn.close()
    print("\n" + "="*50)
    print(" FORENSIC ENRICHMENT COMPLETE")
    print(" Institutional signals synchronized.")
    print("="*50)

if __name__ == "__main__":
    enrich()


if __name__ == "__main__":
    enrich()
