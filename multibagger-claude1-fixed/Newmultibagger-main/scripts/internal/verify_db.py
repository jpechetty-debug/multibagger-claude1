import os
import sqlite3

DB_PATH = os.path.join("runtime", "stocks.db")


def verify():
    if not os.path.exists(DB_PATH):
        print(f"❌ DB not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM multibaggers")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM multibaggers WHERE price = 0 OR price IS NULL")
    zero_price = cur.fetchone()[0]

    cur.execute(
        "SELECT Symbol, Price, Score, Rating, Sector FROM multibaggers ORDER BY Score DESC LIMIT 5"
    )
    top_picks = cur.fetchall()

    print("--- Verification Results ---")
    print(f"Total Records: {total}")
    print(f"Zero Price Records: {zero_price}")
    print("Top 5 Picks:")
    for row in top_picks:
        print(f"  {row[0]}: Price={row[1]}, Score={row[2]}, Rating={row[3]}, Sector={row[4]}")

    conn.close()


if __name__ == "__main__":
    verify()
