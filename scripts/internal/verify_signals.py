
import sqlite3
import os

DB_PATH = os.path.join("runtime", "stocks.db")

def verify():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Check specific bluechips
        tickers = ('RELIANCE.NS', 'TCS.NS', 'SBIN.NS', 'TITAN.NS', 'HDFCBANK.NS')
        cur.execute("SELECT symbol, price, score, rating FROM multibaggers WHERE symbol IN (?, ?, ?, ?, ?)", tickers)
        rows = cur.fetchall()
        
        if not rows:
            print("❌ No bluechip signals found in database.")
        else:
            print("🚀 Institutional Signal Verification:")
            for row in rows:
                print(f"  - {row[0]}: Price={row[1]}, Score={row[2]}, Rating={row[3]}")
                
        conn.close()
    except Exception as e:
        print(f"❌ Verification error: {e}")

if __name__ == "__main__":
    verify()
