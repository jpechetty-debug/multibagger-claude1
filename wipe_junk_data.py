
import sqlite3
import os

DB_PATH = os.path.join("runtime", "stocks.db")

def wipe_junk():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database not found at {DB_PATH}")
        return

    print(f"--- Sanitizing Sovereign Database: {DB_PATH} ---")
    
    try:
        # Create Backup
        import shutil
        backup_path = f"{DB_PATH}.bak"
        if os.path.exists(DB_PATH):
            shutil.copy2(DB_PATH, backup_path)
            print(f"Backup created at {backup_path}")

        if not os.path.exists(DB_PATH):
            print(f"Database not found at {DB_PATH}")
            return

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        
        # Count records to be deleted: 
        # 1. Price is 0 or NULL
        # 2. Score is 0 or NULL
        # 3. Market Cap is 0 or NULL (mandatory field)
        junk_query = "FROM multibaggers WHERE price <= 0 OR price IS NULL OR score <= 0 OR score IS NULL OR market_cap_cr <= 0 OR market_cap_cr IS NULL"
        
        cur.execute(f"SELECT COUNT(*) {junk_query}")
        junk_count = cur.fetchone()[0]
        
        if junk_count == 0:
            print("No junk records detected (Price=0, Score=0, or Null MCAP).")
        else:
            print(f"Found {junk_count} junk records. Purging...")
            cur.execute(f"DELETE {junk_query}")
            conn.commit()
            print(f"Successfully purged {junk_count} records.")
            
        conn.close()
    except Exception as e:
        print(f"❌ Error during sanitation: {e}")

if __name__ == "__main__":
    wipe_junk()
