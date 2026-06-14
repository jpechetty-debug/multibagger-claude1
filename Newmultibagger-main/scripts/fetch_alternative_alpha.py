#!/usr/bin/env python
"""
Fetch Alternative Alpha Data (Phase 2)
Pulls SAST and Block Deals from NSE and stores them in the institutional_flows table.
Schedule to run weekly on Saturdays or daily after market hours.
"""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.repository import get_connection
from db.models import _utc_now
from modules.data_layer.nse_sast_scraper import NSEScraper, parse_nse_date

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def fetch_and_store_flows():
    """Fetch SAST and Block deals, then insert into db."""
    sast_records = []
    block_records = []

    async with NSEScraper() as scraper:
        logger.info("Fetching SAST data...")
        sast_data = await scraper.fetch_sast_data()
        for item in sast_data:
            # item typically has: 'symbol', 'acqName', 'totalShares', 'date', etc.
            symbol = item.get("symbol")
            if not symbol:
                continue

            try:
                date_str = item.get("acqDate", item.get("date", ""))
                execution_date = parse_nse_date(date_str) if date_str else _utc_now().date()

                sast_records.append({
                    "symbol": symbol,
                    "execution_date": execution_date,
                    "transaction_type": "SAST",
                    "party_name": item.get("acqName", "Unknown"),
                    "quantity": float(item.get("totalShares", 0) or 0),
                    "price_per_share": 0.0, # SAST doesn't always have price
                    "value_cr": 0.0
                })
            except Exception as e:
                logger.warning(f"Error parsing SAST item {item}: {e}")

        logger.info("Fetching Block Deals data...")
        block_data = await scraper.fetch_block_deals()
        for item in block_data:
            # item typically has: 'symbol', 'clientName', 'quantity', 'tradePrice', 'date'
            symbol = item.get("symbol")
            if not symbol:
                continue

            try:
                date_str = item.get("date", "")
                execution_date = parse_nse_date(date_str) if date_str else _utc_now().date()
                qty = float(item.get("quantity", 0) or 0)
                price = float(item.get("tradePrice", 0) or 0)

                block_records.append({
                    "symbol": symbol,
                    "execution_date": execution_date,
                    "transaction_type": "BLOCK",
                    "party_name": item.get("clientName", "Unknown"),
                    "quantity": qty,
                    "price_per_share": price,
                    "value_cr": (qty * price) / 10000000.0 # calculate value in Crores
                })
            except Exception as e:
                logger.warning(f"Error parsing Block Deal item {item}: {e}")

    # Insert into DB
    all_records = sast_records + block_records
    if not all_records:
        logger.info("No records found to insert.")
        return

    conn = get_connection()
    try:
        # We can use INSERT OR IGNORE by using a unique index, but since we didn't specify unique on (symbol, execution_date, party_name)
        # we will just insert. In production, we'd want an upsert logic.
        logger.info(f"Inserting {len(all_records)} flow records into DB.")

        insert_sql = """
            INSERT INTO institutional_flows
            (symbol, execution_date, transaction_type, party_name, quantity, price_per_share, value_cr, reported_at)
            VALUES (:symbol, :execution_date, :transaction_type, :party_name, :quantity, :price_per_share, :value_cr, CURRENT_TIMESTAMP)
        """

        conn.executemany(insert_sql, all_records)
        conn.commit()
        logger.info("Successfully saved flow records.")
    except Exception as e:
        logger.error(f"Database error during insertion: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    asyncio.run(fetch_and_store_flows())
