import os
from pathlib import Path
import sqlite3
from modules.runtime_settings import runtime_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]

def resolve_db_path(db_name: str) -> str:
    """
    Resolve a database name to its absolute path in the runtime directory.
    If it's already an absolute path, returns it as is.
    """
    if os.path.isabs(db_name):
        return db_name
    
    # Always prefer the runtime directory for SQLite databases
    runtime_path = PROJECT_ROOT / "runtime" / db_name
    
    # Ensure directory exists
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    
    return str(runtime_path)

def get_db_connection(db_name: str, timeout: int = None):
    """
    Standardized connection factory for any SQLite database in the system.
    Applies WAL mode and busy_timeout.
    """
    path = resolve_db_path(db_name)
    busy_timeout = timeout or runtime_settings.sqlite_busy_timeout_ms
    
    conn = sqlite3.connect(path, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={busy_timeout}")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn
