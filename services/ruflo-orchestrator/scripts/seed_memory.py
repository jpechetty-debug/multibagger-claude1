import sqlite3
import os
import subprocess
import json

DB_PATH = r'../../Newmultibagger-main/runtime/stocks.db'

def run_ruflo_command(cmd_str):
    try:
        # Use shell=True for npx on Windows and pass as string
        result = subprocess.run(
            f"npx ruflo {cmd_str}",
            capture_output=True,
            text=True,
            shell=True
        )
        if result.returncode != 0:
            print(f"Error running ruflo command: {result.stderr}")
        return result.stdout
    except Exception as e:
        print(f"Exception running ruflo command: {e}")
        return None

def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Fetch Avoid (Bad) and Buy/Strong Buy (Good)
    query = """
    SELECT symbol, rating, score, sector, price
    FROM multibaggers
    WHERE rating IN ('Avoid', 'Buy', 'Strong Buy (Elite)')
    """
    cursor.execute(query)
    rows = cursor.fetchall()

    print(f"Found {len(rows)} stocks to ingest.")

    for symbol, rating, score, sector, price in rows:
        label = "G" if "Buy" in rating else "B"
        memory_key = f"label_{symbol}"
        memory_value = {
            "symbol": symbol,
            "rating": rating,
            "label": label,
            "score": score,
            "sector": sector,
            "price": price,
            "source": "Sovereign-Sona-Bridge"
        }
        
        print(f"Ingesting {symbol} ({label})...")
        json_val = json.dumps(memory_value).replace('"', '\\"').replace('&', 'and')
        run_ruflo_command(
            f'memory store --namespace sovereign-labels --key {memory_key} --value "{json_val}"'
        )

    conn.close()
    print("Ingestion complete.")

if __name__ == "__main__":
    main()
