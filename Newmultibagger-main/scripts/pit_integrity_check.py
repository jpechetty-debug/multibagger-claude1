# scripts/pit_integrity_check.py
import sys
import os
from pathlib import Path
import pandas as pd
import logging
from datetime import datetime

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db.repository as repository

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("PITIntegrity")

def run_pit_audit():
    logger.info("Starting PIT Integrity Audit (Look-ahead Bias Detection)...")

    conn = repository.get_connection()
    try:
        # Check for as_of_date < source_updated_at (Potential look-ahead bias)
        # source_updated_at is stored as TIMESTAMP string in SQLite
        query = """
        SELECT symbol, as_of_date, source_updated_at
        FROM fundamentals_pit
        WHERE source_updated_at IS NOT NULL
        """
        df = pd.read_sql(query, conn)

        if df.empty:
            logger.warning("No PIT records with source_updated_at found.")
            return

        # Convert to datetime for comparison
        df['as_of_dt'] = pd.to_datetime(df['as_of_date'])
        df['source_dt'] = pd.to_datetime(df['source_updated_at'])

        # Look-ahead: as_of_date is EARLIER than the date the data was actually published
        # This means the system 'knew' something before it was officially updated in the source.
        # Note: In PIT, as_of_date is the date the signal is generated.
        # If signal date < publication date, it's a leakage.
        leakage = df[df['as_of_dt'] < df['source_dt'].dt.normalize()]

        if not leakage.empty:
            logger.error(f"DETECTED LOOK-AHEAD BIAS: {len(leakage)} records found!")
            for _, row in leakage.head(10).iterrows():
                logger.warning(f"  Symbol: {row['symbol']}, AsOf: {row['as_of_date']}, SourceUpdated: {row['source_updated_at']}")
        else:
            logger.info("No obvious look-ahead bias detected in PIT table.")

        # Check for score drift alerts
        alerts_df = pd.read_sql("SELECT * FROM score_drift_alerts WHERE alert_status = 'OPEN'", conn)
        if not alerts_df.empty:
            logger.warning(f"Active Score Drift Alerts: {len(alerts_df)}")
            unexplained = alerts_df[alerts_df['fundamental_changed'] == 0]
            if not unexplained.empty:
                logger.error(f"  Unexplained Drifts: {len(unexplained)} (potential scoring logic bug)")
        else:
            logger.info("No active score drift alerts.")

    finally:
        conn.close()

if __name__ == "__main__":
    run_pit_audit()
