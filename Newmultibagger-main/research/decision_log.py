from datetime import date
from typing import Optional, List
from pydantic import BaseModel

from db.engine import get_session
from db.models import DecisionLog as DBDecisionLog
from core.observability.logger import get_logger

_log = get_logger("research.decision_log")

class DecisionEntry(BaseModel):
    ticker: str
    decision_date: date
    action: str  # BUY, SELL, ADD, TRIM, HOLD
    reason: str
    expected_cagr: Optional[float] = None


class DecisionLogManager:
    """
    Manages the Decision Log for tracking buys/sells/holds and the reasons why.
    """

    @staticmethod
    def add_decision(entry: DecisionEntry) -> bool:
        try:
            with next(get_session()) as session:
                db_entry = DBDecisionLog(
                    ticker=entry.ticker,
                    decision_date=entry.decision_date,
                    action=entry.action.upper(),
                    reason=entry.reason,
                    expected_cagr=entry.expected_cagr,
                )
                session.add(db_entry)
                session.commit()
                _log.info(f"Saved decision log for {entry.ticker}: {entry.action}.")
            return True
        except Exception as e:
            _log.error(f"Failed to save decision log for {entry.ticker}: {e}")
            return False

    @staticmethod
    def get_decisions(ticker: str = None) -> List[dict]:
        """
        Retrieves the decisions, optionally filtered by ticker.
        """
        results = []
        try:
            with next(get_session()) as session:
                query = session.query(DBDecisionLog)
                if ticker:
                    query = query.filter_by(ticker=ticker)
                entries = query.order_by(DBDecisionLog.decision_date.desc()).all()
                for e in entries:
                    results.append({
                        "id": e.id,
                        "ticker": e.ticker,
                        "decision_date": e.decision_date.isoformat(),
                        "action": e.action,
                        "reason": e.reason,
                        "expected_cagr": e.expected_cagr,
                        "created_at": e.created_at.isoformat() if e.created_at else None,
                    })
        except Exception as e:
            _log.error(f"Failed to retrieve decision log: {e}")

        return results
