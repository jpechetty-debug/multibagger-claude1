import os
import sqlite3

conn = sqlite3.connect("runtime/stocks.db" if os.path.exists("runtime/stocks.db") else "stocks.db")
cur = conn.cursor()
cur.execute("PRAGMA table_info(multibaggers)")
cols = cur.fetchall()
with open("schema_output.txt", "w") as f:
    f.write("multibaggers columns:\n")
    for c in cols:
        f.write(f"  {c[1]:30} {c[2]:15}\n")
    f.write(f"\nTotal columns: {len(cols)}\n")
print(f"Schema written to schema_output.txt ({len(cols)} columns)")
conn.close()
