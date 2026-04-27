
"""
GARP Strategy Module
--------------------
Generates weekly 'ALLOCATION_PROPOSAL' events.
1. Loads Universe (Screener Results / Database)
2. Applies Fundamental Filters
3. Ranks by Conviction Score
4. Emits Top Candidates
"""

import pandas as pd
import sqlite3
import os
import sys

# Add project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.fundamental_filters import validate_garp_criteria
import db.repository as database
import asyncio
from modules.news import get_stock_news

class GarpStrategy:
    def __init__(self, db_path="stocks.db"):
        self.db_path = db_path
        self.candidates = []

    @staticmethod
    def _safe_float(value, default=0.0):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return float(default)
        if pd.isna(parsed):
            return float(default)
        return float(parsed)

    @classmethod
    def _normalize_rs_score(cls, rs_value):
        rs = cls._safe_float(rs_value)
        if rs <= 0:
            return 0.0
        if rs <= 3.05:
            return min(rs * (100.0 / 3.0), 100.0)
        return min(rs, 100.0)

    @classmethod
    def _build_rank_components(cls, stock):
        nexus_score = cls._safe_float(stock.get("score") or stock.get("Score"))
        conviction = cls._safe_float(stock.get("conviction_score") or stock.get("Conviction_Score"))
        rs_score = cls._normalize_rs_score(stock.get("rs_rating") or stock.get("RS_Rating"))
        data_quality = cls._safe_float(stock.get("data_quality") or stock.get("Data_Quality"))

        # Nexus Alpha is the primary engine. Conviction/RS/DQ refine the ordering.
        if nexus_score > 0:
            final_rank_score = (
                nexus_score * 0.60
                + conviction * 0.25
                + rs_score * 0.10
                + data_quality * 0.05
            )
        else:
            final_rank_score = (conviction * 0.70) + (rs_score * 0.30)

        return {
            "rank_score": round(final_rank_score, 1),
            "nexus_score": round(nexus_score, 1),
            "conviction": round(conviction, 1),
            "rs_score": round(rs_score, 1),
            "data_quality": round(data_quality, 1),
        }

    def load_universe(self):
        """Loads latest scanned data from DB."""
        conn = database.get_connection()
        try:
            # Load active stocks with valid price
            query = """
            SELECT * FROM multibaggers 
            WHERE price > 0 
            ORDER BY score DESC
            """
            self.universe = pd.read_sql(query, conn)
        except Exception as e:
            print(f"Error loading universe: {e}")
            self.universe = pd.DataFrame()
        finally:
            conn.close()

    def generate_proposals(self, top_n=20):
        """
        Runs filters and returns top N proposals.
        """
        self.load_universe()
        if self.universe.empty:
            print("Universe empty. Run screener first.")
            return []

        qualified = []
        
        print(f"Scanning {len(self.universe)} stocks for GARP criteria...")
        
        for _, row in self.universe.iterrows():
            stock = row.to_dict()
            is_valid, reason = validate_garp_criteria(stock)
            
            if is_valid:
                components = self._build_rank_components(stock)
                
                qualified.append({
                    "Symbol": stock.get("symbol"),
                    "Rank_Score": components["rank_score"],
                    "Nexus_Score": components["nexus_score"],
                    "Conviction": components["conviction"],
                    "RS_Score": components["rs_score"],
                    "Data_Quality": components["data_quality"],
                    "Price": stock.get("price"),
                    "Reason": "GARP Qualified | Nexus-led composite rank",
                })
        
        # Sort by Rank
        qualified_df = pd.DataFrame(qualified)
        if not qualified_df.empty:
            qualified_df = qualified_df.sort_values(by="Rank_Score", ascending=False).head(top_n)
            final_proposals = qualified_df.to_dict(orient="records")
            
            # Enrich with News (Gate 0 Requirement)
            print(f"Fetching news for {len(final_proposals)} candidates...")
            try:
                # Run async news fetch in sync context
                enriched = asyncio.run(self._fetch_news_batch(final_proposals))
                return enriched
            except Exception as e:
                print(f"News fetch failed: {e}")
                return final_proposals
        
        return []

    async def _fetch_news_batch(self, proposals):
        """
        Fetches news for all proposals in parallel.
        """
        tasks = []
        for p in proposals:
            symbol = p.get('Symbol')
            tasks.append(get_stock_news(symbol))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for p, news in zip(proposals, results):
            if isinstance(news, list):
                p['Recent_News'] = news
            else:
                p['Recent_News'] = [] # On error
                
        return proposals

if __name__ == "__main__":
    strategy = GarpStrategy()
    proposals = strategy.generate_proposals()
    
    print("\n--- GARP Allocation Proposals ---")
    if proposals:
        for i, p in enumerate(proposals):
            print(f"{i+1}. {p['Symbol']} (Rank: {p['Rank_Score']}, Conviction: {p['Conviction']})")
    else:
        print("No candidates found.")
