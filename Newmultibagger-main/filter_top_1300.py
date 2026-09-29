import os
import sys
import sqlite3
import pandas as pd
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    from ticker_list import TICKERS
except ImportError:
    print("Could not import TICKERS")
    sys.exit(1)

print(f"Total starting tickers: {len(TICKERS)}")

market_caps = {}
db_path = 'data/multibaggers.db'
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        tables = pd.read_sql("SELECT name FROM sqlite_master WHERE type='table'", conn)

        table_name = 'multibaggers' if 'multibaggers' in tables['name'].values else None
        if not table_name:
            table_name = 'screener_results' if 'screener_results' in tables['name'].values else None

        if table_name:
            df = pd.read_sql(f"SELECT Symbol, Market_Cap_Cr FROM {table_name}", conn)
            for _, row in df.iterrows():
                sym = str(row['Symbol']).strip().upper()
                mc = row['Market_Cap_Cr']
                if pd.notna(mc) and mc > 0:
                    market_caps[sym] = float(mc)
    except Exception as e:
        print(f"DB Error: {e}")

print(f"Market caps found in DB: {len(market_caps)}")

missing_tickers = [t for t in TICKERS if t.upper() not in market_caps and (t.upper() + ".NS") not in market_caps]
print(f"Missing market caps for {len(missing_tickers)} tickers. Fetching via yfinance...")

def fetch_mc(ticker):
    try:
        sym = ticker if ticker.endswith((".NS", ".BO")) else ticker + ".NS"
        info = yf.Ticker(sym).info
        mc = info.get('marketCap')
        if mc:
            # Convert to crores
            return ticker, mc / 10000000
    except Exception:
        pass
    return ticker, 0

if missing_tickers:
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_mc, t): t for t in missing_tickers}
        for i, future in enumerate(as_completed(futures)):
            t, mc = future.result()
            market_caps[t.upper()] = mc
            if i > 0 and i % 100 == 0:
                print(f"Fetched {i}/{len(missing_tickers)}")

ranked = []
for t in TICKERS:
    tu = t.upper()
    mc = market_caps.get(tu, market_caps.get(tu + ".NS", 0))
    ranked.append((t, mc))

ranked.sort(key=lambda x: x[1], reverse=True)
top_1300 = [x[0] for x in ranked[:1300]]

print(f"Lowest market cap in top 1300: {ranked[1299][1]:.2f} Cr")
print(f"Top 5: {[x[0] for x in ranked[:5]]}")

ticker_list_path = 'ticker_list.py'
with open(ticker_list_path, encoding='utf-8') as f:
    content = f.read()

import re
new_tickers_str = "TICKERS = [\n"
for t in top_1300:
    new_tickers_str += f'    "{t}",\n'
new_tickers_str += "]"

pattern = re.compile(r'TICKERS\s*=\s*\[.*?\]', re.DOTALL)
if pattern.search(content):
    new_content = pattern.sub(new_tickers_str.strip(), content)
    with open(ticker_list_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Successfully updated ticker_list.py")
else:
    print("Could not find TICKERS list in ticker_list.py using regex.")
