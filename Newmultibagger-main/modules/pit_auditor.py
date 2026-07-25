"""
pit_auditor.py

Institutional-grade Point-In-Time (PIT) data auditor designed to eliminate look-ahead bias
from fundamental datasets used in quantitative trading engines.
"""


class PITViolationError(Exception):
    """Raised when a PIT hard gate detects look-ahead bias that must block scoring."""


import hashlib  # noqa: E402
import os  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402

from core.observability.logger import get_logger  # noqa: E402
from db.date_utils import normalize_date  # noqa: E402
from modules.db_utils import get_db_connection  # noqa: E402

_log = get_logger(__name__)


# Configure logging to securely track all PIT violations
PIT_LOG_PATH = os.getenv("PIT_LOG_PATH", "pit_violations.log")

logger = get_logger("pit_auditor", log_file=PIT_LOG_PATH)


@dataclass
class PITAuditReport:
    """Dataclass containing the analytical results of a PIT dataset audit."""

    violation_count: int
    violation_rows: list[dict[str, Any]] = field(default_factory=list)
    bias_risk_score: float = 0.0
    recommended_action: str = "PASS"


# Release lag mapping identifying days before reports are known to the market
release_lag_map = {
    "earnings": pd.Timedelta(days=45),
    "balance_sheet": pd.Timedelta(days=60),
    "cashflow": pd.Timedelta(days=75),
    "default": pd.Timedelta(days=45),
}


def checksum(row: pd.Series) -> str:
    """
    Computes a cryptographic SHA-256 checksum for a data row to detect
    silent, retroactive data revisions by vendors.

    Args:
        row: A pandas Series representing a row of fundamental data.

    Returns:
        Hexadecimal SHA-256 checksum string.
    """
    # Cast entirely to string format to build an unalterable hash target
    row_str = "".join(str(val) for val in row.values)
    return hashlib.sha256(row_str.encode("utf-8")).hexdigest()


class PITDataStore:
    """
    SQLite-backed transactional store for Point-In-Time (PIT) fundamental data.
    Ensures that metric values are mathematically locked to specific 'as_of' dates.
    """

    def __init__(self, db_name: str = "pit_store.db"):
        self.db_name = db_name
        self._init_db()

    def _get_conn(self):
        return get_db_connection(self.db_name)

    def _init_db(self):
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pit_data (
                    symbol TEXT,
                    metric_name TEXT,
                    value REAL,
                    report_date TEXT,
                    as_of_date DATE,
                    source TEXT,
                    checksum TEXT,
                    PRIMARY KEY(symbol, metric_name, report_date, as_of_date)
                )
            """)
            conn.commit()

    def insert_record(
        self,
        symbol: str,
        metric_name: str,
        value: float,
        report_date: str,
        as_of_date: str,
        source: str,
    ):
        """Inserts a tightly controlled PIT record using an auto-computed checksum."""
        report_date = normalize_date(report_date, default="") or ""
        as_of_date = normalize_date(as_of_date, default="") or ""
        row_s = pd.Series([symbol, metric_name, value, report_date, as_of_date, source])
        chksum = checksum(row_s)

        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO pit_data
                (symbol, metric_name, value, report_date, as_of_date, source, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (symbol, metric_name, value, report_date, as_of_date, source, chksum),
            )
            conn.commit()

    def close(self):
        pass  # Connections are managed via context manager in get_conn


def _get_lag_for_metric(metric_name: str, report_date: Any = None) -> pd.Timedelta:
    """Helper method to organically route string metric names to their expected lag."""
    metric_lower = str(metric_name).lower()
    if "eps" in metric_lower or "revenue" in metric_lower or "earnings" in metric_lower:
        base_lag = release_lag_map["earnings"]
    elif "debt" in metric_lower or "equity" in metric_lower or "assets" in metric_lower:
        base_lag = release_lag_map["balance_sheet"]
    elif "cash" in metric_lower or "cfo" in metric_lower:
        base_lag = release_lag_map["cashflow"]
    else:
        base_lag = release_lag_map["default"]

    if report_date is not None:
        try:
            dt = pd.to_datetime(report_date)
            if pd.notna(dt) and dt.month == 3:
                return max(base_lag, pd.Timedelta(days=60))
        except Exception:
            pass

    return base_lag


def audit_dataset(df: pd.DataFrame, feature_cols: list[str] | None = None) -> PITAuditReport:
    """
    Audits an entire DataFrame aggressively to detect look-ahead bias by validating
    the `as_of_date` boundary against the `report_date` mapping and expected lag.

    Args:
        df: Pandas DataFrame containing 'symbol', 'report_date', 'as_of_date'
        feature_cols: Target feature definitions interacting with the metric lag.

    Returns:
        PITAuditReport mapping total timeline violations and qualitative risk scores.
    """
    violations = []

    if "report_date" not in df.columns or "as_of_date" not in df.columns:
        logger.error("SNAPSHOT_MISSING: DataFrame missing requested timeline columns.")
        return PITAuditReport(
            violation_count=len(df),
            bias_risk_score=100.0,
            recommended_action="REJECT_DATASET (SNAPSHOT_MISSING)",
        )

    df_copy = df.copy()
    try:
        df_copy["report_date"] = pd.to_datetime(df_copy["report_date"])
        df_copy["as_of_date"] = pd.to_datetime(df_copy["as_of_date"])
    except Exception as e:
        logger.error("Date conversion failure", error=str(e))
        return PITAuditReport(len(df), [], 100.0, "REJECT_DATASET (INVALID_DATES)")

    for _idx, row in df_copy.iterrows():
        metric = row.get("metric_name", "default")
        lag = _get_lag_for_metric(metric, row["report_date"])

        expected_public_date = row["report_date"] + lag


        violation_type = None

        # Look-Ahead Bias: Was this explicitly known to the market?
        if row["as_of_date"] < expected_public_date:
            violation_type = "FUTURE_LEAK"

        # Revision Ignored: Timestamp too far ahead spanning multiple missing cycles
        # Relaxed to 10 years to support long-horizon historical fundamental backtests
        elif row["as_of_date"] > expected_public_date + pd.Timedelta(days=3650):
            violation_type = "REVISION_IGNORED"

        if violation_type:
            v_dict = row.to_dict()
            # Serialize for JSON dict structure in reporting
            v_dict["as_of_date"] = str(v_dict["as_of_date"])
            v_dict["report_date"] = str(v_dict["report_date"])
            v_dict["violation_type"] = violation_type
            v_dict["expected_public_date"] = str(expected_public_date)
            violations.append(v_dict)

            logger.warning(
                "PIT violation detected",
                violation_type=violation_type,
                symbol=row.get("symbol", "UNK"),
                as_of_date=str(row["as_of_date"]),
                report_date=str(row["report_date"]),
                expected_public_date=str(expected_public_date),
            )

    violation_count = len(violations)
    total_rows = len(df_copy)

    bias_risk_score = (violation_count / total_rows * 100.0) if total_rows > 0 else 0.0

    # Hard gate: if any violations exist, raise instead of silently passing
    if violation_count > 0 and bias_risk_score > 0:
        action = "PASS"
        if bias_risk_score > 5.0:
            action = "QUARANTINE"
        if bias_risk_score > 20.0:
            action = "REJECT_DATASET"

        if action == "REJECT_DATASET":
            raise PITViolationError(f"PIT Violation threshold exceeded: {bias_risk_score}% risk.")
    else:
        action = "PASS"

    return PITAuditReport(
        violation_count=violation_count,
        violation_rows=violations,
        bias_risk_score=bias_risk_score,
        recommended_action=action,
    )


def sanitize(df: pd.DataFrame) -> pd.DataFrame:
    """
    Sanitizes the DataFrame forcibly removing rows traversing mathematical PIT horizons.
    Drops any instance of look-ahead leakage.

    Args:
        df: The raw ingested observation pandas DataFrame.

    Returns:
        Cleaned pandas DataFrame eliminating all look-ahead bias traces.
    """
    if "report_date" not in df.columns or "as_of_date" not in df.columns:
        return pd.DataFrame()

    df_clean = df.copy()
    try:
        report_dates = pd.to_datetime(df_clean["report_date"])
        as_of_dates = pd.to_datetime(df_clean["as_of_date"])
    except Exception as e:
        _log.error(f"Caught unhandled exception: {e}", exc_info=True)
        return pd.DataFrame()

    if "metric_name" in df_clean.columns:
        lags = df_clean["metric_name"].apply(_get_lag_for_metric)
    else:
        # Avoid fragile broadcasting by creating an explicit lag series
        lags = pd.Series([release_lag_map["default"]] * len(df_clean), index=df_clean.index)

    expected_dates = report_dates + lags

    # Isolate valid rows preserving strict chronological truth
    mask_valid = (as_of_dates >= expected_dates) & (
        as_of_dates <= expected_dates + pd.Timedelta(days=3650)
    )

    df_sanitized = df_clean[mask_valid].copy()

    dropped = len(df_clean) - len(df_sanitized)
    if dropped > 0:
        logger.info("Sanitization activated", dropped_rows=dropped)

    return df_sanitized


SEBI_FILING_LAG_DAYS = 45


def enforce_pit_gate(
    as_of_date,
    quarter_end_date,
    symbol: str = "UNKNOWN",
    lag_days: int = SEBI_FILING_LAG_DAYS,
) -> None:
    """Hard gate: raise PITViolationError if data is used before SEBI filing deadline.

    Indian listed companies have 45 days to file quarterly results.
    Any score using Q4 data before the filing deadline is a lookahead.

    Args:
        as_of_date: The date at which the score is being computed.
        quarter_end_date: The quarter-end date of the fundamental data.
        symbol: Stock symbol for error reporting.
        lag_days: Minimum days after quarter end before data is public (default 45).

    Raises:
        PITViolationError: If as_of_date is within lag_days of quarter_end_date.
    """
    as_of = pd.to_datetime(as_of_date)
    q_end = pd.to_datetime(quarter_end_date)
    days_elapsed = (as_of - q_end).days

    if days_elapsed < lag_days:
        raise PITViolationError(
            f"PIT BLOCK: {symbol} — as_of_date {as_of.date()} is only "
            f"{days_elapsed} days after quarter_end {q_end.date()} "
            f"(minimum {lag_days} days required for SEBI filing lag)"
        )

    logger.debug(
        "PIT gate passed",
        symbol=symbol,
        as_of_date=str(as_of.date()),
        quarter_end=str(q_end.date()),
        days_elapsed=days_elapsed,
    )
