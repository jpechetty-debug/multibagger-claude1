import sqlite3
import os

db_path = r'Newmultibagger-main\runtime\stocks.db'

if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    print("Rating distribution:")
    results = conn.execute("SELECT rating, COUNT(*) FROM multibaggers GROUP BY rating").fetchall()
    for rating, count in results:
        print(f"  {rating}: {count}")
    
    print("\nData for failing symbols:")
    fails = ['ATLANTAELE.NS', 'PRECWIRE.NS', 'POWERINDIA.NS']
    for sym in fails:
        row = conn.execute("SELECT symbol, sector, price, score FROM multibaggers WHERE symbol=?", (sym,)).fetchone()
        print(f"  {row}")
        
    conn.close()
else:
    print(f"Database not found at {db_path}")
