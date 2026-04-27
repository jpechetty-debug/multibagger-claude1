import os
import sqlite3

conn = sqlite3.connect("runtime/stocks.db" if os.path.exists("runtime/stocks.db") else "stocks.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("Tables:", [t[0] for t in tables])
for t in tables:
    count = conn.execute(f"SELECT count(*) FROM {t[0]}").fetchone()[0]
    print(f"  {t[0]}: {count} rows")
conn.close()
