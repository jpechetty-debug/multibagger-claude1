import sqlite3
import os

db_paths = [
    'stocks.db',
    'Newmultibagger-main/stocks.db',
    'Newmultibagger-main/runtime/stocks.db',
    'runtime/stocks.db'
]

for path in db_paths:
    if os.path.exists(path):
        print(f"\nChecking {path}...")
        try:
            conn = sqlite3.connect(path)
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            print(f"Tables: {tables}")
            for table in tables:
                table_name = table[0]
                count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                print(f"  {table_name}: {count} rows")
            conn.close()
        except Exception as e:
            print(f"Error checking {path}: {e}")
    else:
        print(f"\n{path} does not exist.")
