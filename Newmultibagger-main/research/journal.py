from datetime import date
from typing import Optional, List
from pydantic import BaseModel

from db.engine import get_session
from db.models import ResearchJournal as DBResearchJournal
from core.observability.logger import get_logger

_log = get_logger("research.journal")

class JournalEntry(BaseModel):
    ticker: str
    entry_date: date
    observation: str
    decision: Optional[str] = None
    outcome: Optional[str] = None


class JournalManager:
    """
    Manages Research Journal entries.
    """

    @staticmethod
    def add_entry(entry: JournalEntry) -> bool:
        try:
            with next(get_session()) as session:
                db_entry = DBResearchJournal(
                    ticker=entry.ticker,
                    entry_date=entry.entry_date,
                    observation=entry.observation,
                    decision=entry.decision,
                    outcome=entry.outcome,
                )
                session.add(db_entry)
                session.commit()
                _log.info(f"Saved journal entry for {entry.ticker}.")
            return True
        except Exception as e:
            _log.error(f"Failed to save journal entry for {entry.ticker}: {e}")
            return False

    @staticmethod
    def get_entries(ticker: str) -> List[dict]:
        """
        Retrieves the journal entries for a ticker.
        """
        results = []
        try:
            with next(get_session()) as session:
                entries = session.query(DBResearchJournal).filter_by(ticker=ticker).order_by(DBResearchJournal.entry_date.desc()).all()
                for e in entries:
                    results.append({
                        "id": e.id,
                        "ticker": e.ticker,
                        "entry_date": e.entry_date.isoformat(),
                        "observation": e.observation,
                        "decision": e.decision,
                        "outcome": e.outcome,
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                    })
        except Exception as e:
            _log.error(f"Failed to retrieve journal entries for {ticker}: {e}")

        return results
