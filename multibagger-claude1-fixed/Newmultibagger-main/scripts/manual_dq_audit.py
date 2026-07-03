# scripts/manual_dq_audit.py
import sys
import os
from pathlib import Path
import pandas as pd
import logging

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db.repository as repository
from modules.dq_gates import validate_dataframe

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ManualDQAudit")

def run_audit():
    logger.info("Starting Manual DQ Audit...")

    conn = repository.get_connection()
    try:
        # 1. Audit Multibaggers Table
        logger.info("Auditing 'multibaggers' table...")
        df_mb = pd.read_sql("SELECT * FROM multibaggers", conn)
        if not df_mb.empty:
            df_mb = validate_dataframe(df_mb)
            avg_quality = df_mb['data_quality'].mean()
            toxic_count = len(df_mb[df_mb['data_quality'] < 70])
            logger.info(f"Multibaggers Audit: Avg Quality={avg_quality:.2f}, Toxic Tickers={toxic_count}/{len(df_mb)}")

            if toxic_count > 0:
                logger.warning("Sample Toxic Tickers (flags):")
                toxic_sample = df_mb[df_mb['data_quality'] < 70].head(5)
                for _, row in toxic_sample.iterrows():
                    logger.warning(f"  {row['symbol']}: Quality={row['data_quality']} Flags={row.get('data_quality_flags', 'N/A')}")
        else:
            logger.warning("Multibaggers table is empty.")

        # 2. Audit Fundamentals PIT Table
        logger.info("Auditing 'fundamentals_pit' table...")
        df_pit = pd.read_sql("SELECT * FROM fundamentals_pit", conn)
        if not df_pit.empty:
            df_pit = validate_dataframe(df_pit)
            avg_quality_pit = df_pit['data_quality'].mean()
            toxic_count_pit = len(df_pit[df_pit['data_quality'] < 70])
            logger.info(f"Fundamentals PIT Audit: Avg Quality={avg_quality_pit:.2f}, Toxic Tickers={toxic_count_pit}/{len(df_pit)}")
        else:
            logger.warning("Fundamentals PIT table is empty.")

    finally:
        conn.close()

if __name__ == "__main__":
    run_audit()
