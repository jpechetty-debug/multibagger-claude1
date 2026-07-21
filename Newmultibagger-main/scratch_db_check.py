import sqlite3
import datetime
from pathlib import Path

db_path = Path("d:/Tradeidesa/Multibagger-claude/Newmultibagger-main/multibaggers.db")
if db_path.exists():
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # Find tables
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print("Tables:", tables)

        # If 'stocks' or something exists, count fresh vs stale
        if "stocks" in tables:
            rows = cur.execute("SELECT COUNT(*) FROM stocks").fetchone()
            print("Total in stocks table:", rows[0])

        if "data_intelligence" in tables:
            rows = cur.execute("SELECT * FROM data_intelligence").fetchall()
            print("data_intelligence:", rows)
    except Exception as e:
        print("Error:", e)
else:
    print("DB not found at", db_path)
