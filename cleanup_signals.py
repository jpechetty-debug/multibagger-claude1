import sqlite3
import os

db_path = "stocks.db"
print(f"Checking database at {os.path.abspath(db_path)}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check current signals
cursor.execute("SELECT symbol FROM multibaggers")
all_symbols = [row[0] for row in cursor.fetchall()]
print(f"All symbols: {all_symbols}")

to_delete = [s for s in all_symbols if "AAA" in s or "BBB" in s]
print(f"Symbols to delete: {to_delete}")

if to_delete:
    cursor.execute(f"DELETE FROM multibaggers WHERE symbol IN ({','.join(['?']*len(to_delete))})", to_delete)
    
    # Also clean up PIT data
    cursor.execute(f"DELETE FROM fundamentals_pit WHERE symbol IN ({','.join(['?']*len(to_delete))})", to_delete)
    
    conn.commit()
    print(f"Deleted {len(to_delete)} signals.")
else:
    print("No matching signals found.")

conn.close()
