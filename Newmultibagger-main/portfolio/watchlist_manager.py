from datetime import datetime
from typing import List
from db.engine import get_session
from db.models import Watchlist as DBWatchlist
from core.observability.logger import get_logger

_log = get_logger("portfolio.watchlist_manager")

VALID_STATES = [
    "Research",
    "Watchlist",
    "Accumulation",
    "Core Holding",
    "Review",
    "Exit Candidate",
    "Archived"
]

class WatchlistManager:
    """
    Manages the lifecycle state of a stock.
    """

    @staticmethod
    def update_state(ticker: str, new_state: str, notes: str = None) -> bool:
        if new_state not in VALID_STATES:
            _log.error(f"Invalid state: {new_state}. Valid states: {VALID_STATES}")
            return False

        try:
            with next(get_session()) as session:
                entry = session.query(DBWatchlist).filter_by(ticker=ticker).first()
                if entry:
                    entry.state = new_state
                    if notes:
                        entry.notes = notes
                    entry.entered_state_at = datetime.utcnow()
                else:
                    entry = DBWatchlist(
                        ticker=ticker,
                        state=new_state,
                        notes=notes
                    )
                    session.add(entry)
                session.commit()
                _log.info(f"Updated {ticker} to {new_state}")
            return True
        except Exception as e:
            _log.error(f"Failed to update watchlist state for {ticker}: {e}")
            return False

    @staticmethod
    def get_portfolio() -> dict:
        """
        Retrieves all tickers grouped by state.
        """
        portfolio = {state: [] for state in VALID_STATES}
        try:
            with next(get_session()) as session:
                entries = session.query(DBWatchlist).all()
                for e in entries:
                    if e.state in portfolio:
                        portfolio[e.state].append({
                            "ticker": e.ticker,
                            "entered_state_at": e.entered_state_at.isoformat() if e.entered_state_at else None,
                            "notes": e.notes
                        })
        except Exception as e:
            _log.error(f"Failed to retrieve portfolio states: {e}")
        return portfolio
