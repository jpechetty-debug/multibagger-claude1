from datetime import date
from typing import Optional, List
from pathlib import Path
from pydantic import BaseModel

from db.engine import get_session
from db.models import KnowledgeEntry as DBKnowledgeEntry
from core.observability.logger import get_logger

_log = get_logger("research.knowledge_base")

ARTIFACTS_DIR = Path("artifacts/research_memos")

class KnowledgeEntry(BaseModel):
    ticker: str
    source_type: str  # e.g., 'Concall', 'Annual Report', 'Management Commentary', 'Scuttlebutt'
    source_date: date
    summary: str
    tags: Optional[str] = None


class KnowledgeBaseManager:
    """
    Manages Knowledge Entries (Concall notes, Annual Reports, etc.)
    using Hybrid Storage (SQLite for metadata, Markdown for full content).
    """

    @staticmethod
    def add_entry(entry: KnowledgeEntry, full_markdown_content: str) -> bool:
        # 1. SQLite Storage
        try:
            with next(get_session()) as session:
                db_entry = DBKnowledgeEntry(
                    ticker=entry.ticker,
                    source_type=entry.source_type,
                    source_date=entry.source_date,
                    summary=entry.summary,
                    tags=entry.tags,
                )
                session.add(db_entry)
                session.commit()
                _log.info(f"Saved knowledge entry for {entry.ticker} to SQLite.")
        except Exception as e:
            _log.error(f"Failed to save knowledge entry to DB for {entry.ticker}: {e}")
            return False

        # 2. Markdown Storage
        try:
            ticker_dir = ARTIFACTS_DIR / entry.ticker
            ticker_dir.mkdir(parents=True, exist_ok=True)
            
            # Format filename to be safe and unique enough
            safe_type = entry.source_type.replace(" ", "_").lower()
            date_str = entry.source_date.strftime("%Y%m%d")
            filename = f"kb_{date_str}_{safe_type}.md"
            file_path = ticker_dir / filename
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(full_markdown_content)
            _log.info(f"Saved full markdown knowledge entry for {entry.ticker} to {file_path}")
        except Exception as e:
            _log.error(f"Failed to save knowledge markdown for {entry.ticker}: {e}")
            return False

        return True

    @staticmethod
    def get_entries(ticker: str) -> List[dict]:
        """
        Retrieves the structured knowledge entries from SQLite for a ticker.
        """
        results = []
        try:
            with next(get_session()) as session:
                entries = session.query(DBKnowledgeEntry).filter_by(ticker=ticker).order_by(DBKnowledgeEntry.source_date.desc()).all()
                for e in entries:
                    results.append({
                        "id": e.id,
                        "ticker": e.ticker,
                        "source_type": e.source_type,
                        "source_date": e.source_date.isoformat(),
                        "summary": e.summary,
                        "tags": e.tags.split(",") if e.tags else [],
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                    })
        except Exception as e:
            _log.error(f"Failed to retrieve knowledge entries from DB for {ticker}: {e}")

        return results
