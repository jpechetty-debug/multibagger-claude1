import hashlib
from db.db_core import execute_sql

def run_migration():
    commands = [
        "ALTER TABLE api_keys ADD COLUMN key_hash TEXT;",
        "ALTER TABLE api_keys ADD COLUMN rate_limit_rpm INTEGER DEFAULT 60;",
        "ALTER TABLE api_keys ADD COLUMN total_usage INTEGER DEFAULT 0;",
        "ALTER TABLE api_keys ADD COLUMN updated_at TEXT;"
    ]

    for cmd in commands:
        try:
            execute_sql(cmd)
            print(f"Executed: {cmd}")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print(f"Skipped (already exists): {cmd}")
            else:
                print(f"Error executing {cmd}: {e}")

    # Update key hashes using Python instead of relying on SQLite extensions
    try:
        keys = execute_sql("SELECT id, key FROM api_keys", fetch_all=True)
        print(f"Found {len(keys)} API keys to migrate.")

        for k in keys:
            key_id = k["id"]
            key_val = k["key"]
            if key_val:
                key_hash = hashlib.sha256(key_val.encode(), usedforsecurity=False).hexdigest()
                execute_sql("UPDATE api_keys SET key_hash = :hash WHERE id = :id", {"hash": key_hash, "id": key_id})
        print("Successfully updated key hashes.")
    except Exception as e:
        print(f"Error updating key hashes: {e}")

if __name__ == "__main__":
    run_migration()
