import sqlite3

def check_db():
    try:
        conn = sqlite3.connect('.claude/memory.db')
        cursor = conn.cursor()
        
        # Check tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        print(f"Tables: {tables}")
        
        for table in tables:
            t_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {t_name}")
            count = cursor.fetchone()[0]
            print(f"  Table {t_name}: {count} rows")
            
            # Print sample
            if count > 0:
                cursor.execute(f"SELECT * FROM {t_name} LIMIT 1")
                sample = cursor.fetchone()
                print(f"    Sample: {sample}")
        
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_db()
