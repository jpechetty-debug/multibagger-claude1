from datetime import date
from typing import Any, Optional
import pandas as pd
from sqlalchemy import text

from modules.domain.company import CompanySnapshot

class SnapshotBuilder:
    """
    Builds a CompanySnapshot for a given symbol and date.
    Retrieves historical Point-in-Time data from the database.
    """

    def __init__(self, db_connection):
        self.conn = db_connection

    def build(self, symbol: str, as_of_date: date) -> Optional[CompanySnapshot]:
        """
        Construct a CompanySnapshot strictly avoiding lookahead bias.
        """
        # Fetch fundamental data known precisely on or before the as_of_date
        financials = self._fetch_fundamentals(symbol, as_of_date)
        if not financials:
            return None
            
        prices = self._fetch_prices(symbol, as_of_date)
        
        # Placeholder for scoring and feature generation which will be moved here
        # in upcoming modularization.
        features = {}
        scores = {}

        return CompanySnapshot(
            symbol=symbol,
            as_of_date=as_of_date,
            financials=financials,
            prices=prices,
            features=features,
            scores=scores
        )

    def _fetch_fundamentals(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        """
        Retrieves the most recent fundamental data filed ON OR BEFORE the as_of_date.
        """
        query = text("""
            SELECT * FROM fundamentals_pit 
            WHERE symbol = :symbol 
              AND as_of_date <= :as_of_date
            ORDER BY as_of_date DESC 
            LIMIT 1
        """)
        
        try:
            df = pd.read_sql(query, self.conn, params={"symbol": symbol, "as_of_date": as_of_date.isoformat()})
            if not df.empty:
                return df.iloc[0].to_dict()
        except Exception:
            pass
        return {}

    def _fetch_prices(self, symbol: str, as_of_date: date) -> dict[str, Any]:
        """
        Retrieves the closing price exact as of the provided date.
        """
        # A full price history table would ideally be queried here.
        # Fallback to current behavior for now.
        return {}
