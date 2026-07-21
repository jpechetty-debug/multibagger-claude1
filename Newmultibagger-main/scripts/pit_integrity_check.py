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
from modules.data_layer.temporal_realignment import TemporalRealignmentEngine


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

        # Realignment engine check (simulate applying lag to publication date)
        realignment_engine = TemporalRealignmentEngine(publishing_lag_days=45)
        # Theoretically, a signal date should not be before the published date + 45 days
        # To test the logic, we simulate pushing the source_dt forward by 45 days.
        # But look-ahead is strictly as_of_date < source_updated_at.
        # Realignment violation is as_of_date < (source_updated_at + 45 days)

        leakage = df[df['as_of_dt'] < df['source_dt'].dt.normalize()]

        if not leakage.empty:
            logger.error(f"DETECTED STRICT LOOK-AHEAD BIAS: {len(leakage)} records found where signal is generated before publication!")
            for _, row in leakage.head(10).iterrows():
                logger.warning(f"  Symbol: {row['symbol']}, AsOf: {row['as_of_date']}, SourceUpdated: {row['source_updated_at']}")
        else:
            logger.info("No strict look-ahead bias detected in PIT table.")

        # Check Temporal Realignment Compliance
        # We need to simulate how the engine works
        aligned_df = realignment_engine.align_fundamentals(df, date_column="source_updated_at")
        aligned_df['aligned_source_dt'] = pd.to_datetime(aligned_df['source_updated_at'])

        # Check if any as_of_date is before the aligned source date (meaning lag wasn't respected)
        unaligned = aligned_df[aligned_df['as_of_dt'] < aligned_df['aligned_source_dt'].dt.normalize()]

        if not unaligned.empty:
            logger.warning(f"DETECTED {len(unaligned)} RECORDS FAILING TEMPORAL REALIGNMENT (45-day lag not respected).")
        else:
            logger.info("Temporal Realignment looks consistent across the board.")

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
