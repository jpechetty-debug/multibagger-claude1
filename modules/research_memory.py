import sqlite3
import os
import datetime
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime", "research_memory.db")

class MemoryManager:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initializes the SQLite database with FTS5 virtual table for lightning-fast keyword research memory."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_name TEXT NOT NULL,
                    symbol TEXT,
                    query TEXT,
                    report TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create FTS (Full Text Search) table for 'observations'
            cursor.execute('''
                CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts 
                USING fts5(tool_name, symbol, query, report, content=observations, content_rowid=id)
            ''')
            
            # Triggers to keep FTS synched with base table
            cursor.executescript('''
                CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
                    INSERT INTO observations_fts(rowid, tool_name, symbol, query, report)
                    VALUES (new.id, new.tool_name, new.symbol, new.query, new.report);
                END;
                CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
                    INSERT INTO observations_fts(observations_fts, rowid, tool_name, symbol, query, report)
                    VALUES('delete', old.id, old.tool_name, old.symbol, old.query, old.report);
                END;
                CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
                    INSERT INTO observations_fts(observations_fts, rowid, tool_name, symbol, query, report)
                    VALUES('delete', old.id, old.tool_name, old.symbol, old.query, old.report);
                    INSERT INTO observations_fts(rowid, tool_name, symbol, query, report)
                    VALUES (new.id, new.tool_name, new.symbol, new.query, new.report);
                END;
            ''')
            conn.commit()

    def record_observation(self, tool_name: str, report: str, symbol: Optional[str] = None, query: Optional[str] = None) -> int:
        """Saves a research outcome into persistent memory."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO observations (tool_name, symbol, query, report) VALUES (?, ?, ?, ?)",
                (tool_name, symbol, query, report)
            )
            conn.commit()
            return cursor.lastrowid

    def search_index(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Progressive Disclosure Step 1: Search the index to return lightweight snippets with IDs."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Escape double quotes for FTS
            clean_query = query.replace('"', '""')
            
            # Match query using FTS MATCH
            # If query is empty, just return the most recent observations
            if not query.strip():
                cursor.execute('''
                    SELECT id, tool_name, symbol, substr(report, 1, 100) as snippet, timestamp
                    FROM observations 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                ''', (limit,))
            else:
                try:
                    cursor.execute('''
                        SELECT id, tool_name, symbol, snippet(observations_fts, 3, '<b>', '</b>', '...', 20) as snippet,
                               (SELECT timestamp FROM observations WHERE id = observations_fts.rowid) as timestamp
                        FROM observations_fts 
                        WHERE observations_fts MATCH ? 
                        ORDER BY rank 
                        LIMIT ?
                    ''', (f'"{clean_query}"', limit))
                except sqlite3.OperationalError:
                    # Fallback to standard LIKE if FTS fails due to bad syntax (e.g. trailing OR)
                    likestr = f"%{query}%"
                    cursor.execute('''
                        SELECT id, tool_name, symbol, substr(report, 1, 100) as snippet, timestamp
                        FROM observations
                        WHERE report LIKE ? OR query LIKE ? OR symbol LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    ''', (likestr, likestr, likestr, limit))
            
            return [dict(row) for row in cursor.fetchall()]

    def get_timeline(self, symbol: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Progressive Disclosure Step 1.5: Fetch chronological timeline of analysis over a particular holding."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, tool_name, timestamp, substr(report, 1, 100) || '...' as snippet
                FROM observations
                WHERE symbol = ? OR symbol LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (symbol, f"%{symbol}%", limit))
            return [dict(row) for row in cursor.fetchall()]

    def fetch_observations(self, ids: List[int]) -> List[Dict[str, Any]]:
        """Progressive Disclosure Step 2: Fetch the full details of specific observation IDs."""
        if not ids:
            return []
        
        placeholders = ','.join('?' * len(ids))
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(f'''
                SELECT id, tool_name, symbol, query, report, timestamp
                FROM observations
                WHERE id IN ({placeholders})
            ''', tuple(ids))
            return [dict(row) for row in cursor.fetchall()]
