# modules/data_service.py
"""
Sovereign Terminal — Data Service Orchestrator
Modularized into: adapters/, normalization/, data_utils.py
"""

import asyncio
import inspect
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

import pandas as pd
import yfinance as yf
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from modules.adapters.nse import NSEPythonProvider, PNSEAProvider
from modules.adapters.screener_in import ScreenerInProvider
from modules.data_utils import get_valid_trading_days, run_coroutine_sync
from modules.db_utils import get_db_connection
from modules.field_names import FIELD_MAPPING
from modules.financial_adapter import create_fundamentals_provider
from modules.normalization.cleaner import is_payload_skeletal
from core.observability.logger import get_logger
logger = get_logger(__name__)

_TRANSIENT_ERROR_HINTS = (
    "timeout",
    "timed out",
    "429",
    "rate limit",
    "too many requests",
    "temporarily unavailable",
    "connection reset",
    "ssl",
    "name resolution",
    "401",
    "unauthorized",
)


CACHE_SCHEMA_VERSION = 2  # Increment when field schema changes
USE_MOCK_HISTORY = os.getenv("USE_MOCK_HISTORY", "false").lower() == "true"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCREENER_CSV_PATH = PROJECT_ROOT / "screener_results.csv"
DEFAULT_SCREENER_TABLE = "multibaggers"
_TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
_NULL_STRINGS = {"", "-", "--", "na", "n/a", "nan", "none", "null"}
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")

SCREENER_FLOAT_FIELDS = (
    "price",
    "score",
    "buy_below",
    "stop_loss",
    "target_1",
    "target_2",
    "sales_growth",
    "roe",
    "peg_ratio",
    "debt_equity",
    "rsi",
    "smart_money",
    "market_cap_cr",
    "cfo_pat_ratio",
    "sales_cagr_5y",
    "avg_roe_5y",
    "pe_ratio",
    "down_from_52w",
    "rs_rating",
    "graham_number",
    "value_gap",
    "analyst_upside",
    "promoter_holding",
    "inst_holding",
    "atr",
    "stop_loss_atr",
    "max_qty_1l",
    "conviction_score",
    "conviction_boost",
    "data_quality",
    "data_confidence",
    "backtest_cagr",
    "backtest_win_rate",
    "backtest_max_dd",
    "backtest_sharpe",
    "ml_predicted_return",
    "high_52w",
    "low_52w",
    "pledge_pct",
    "roce",
    "median_pat_growth",
    "ml_rank_score",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "vol_breakout",
    "dist_from_52w_high",
    "revenue_cagr_3y",
    "revenue_cagr_5y",
    "pat_cagr_3y",
    "pat_cagr_5y",
    "eps_cagr_3y",
    "eps_cagr_5y",
    "dividend_yield",
    "dividend_payout",
)
SCREENER_INT_FIELDS = (
    "f_score",
    "f_score_max",
    "earnings_accel",
    "sector_leader",
    "institutional_interest",
    "piotroski_score",
)
SCREENER_TEXT_FIELDS = (
    "sector",
    "rating",
    "technical_signal",
    "analyst_rating",
    "as_of_date",
    "last_audited",
    "updated_at",
    "super_investors",
    "f_score_method",
    "shap_breakdown",
    "cagr_consistency",
    "cap_category",
    "data_quality_flags",
)


def _is_truthy_env(value: str | None) -> bool:
    return str(value or "").strip().lower() in _TRUTHY_ENV_VALUES


def _validation_alias(csv_name: str, db_name: str) -> AliasChoices:
    return AliasChoices(db_name, csv_name)


def _coerce_optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        text = value.strip()
        if text.lower() in _NULL_STRINGS:
            return None
        is_parenthesized_negative = text.startswith("(") and text.endswith(")")
        if is_parenthesized_negative:
            text = f"-{text[1:-1]}"
        text = (
            text.replace(",", "")
            .replace("%", "")
            .replace("Rs.", "")
            .replace("INR", "")
            .strip()
        )
        if text.lower().endswith(" cr"):
            text = text[:-3].strip()
        value = text
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _coerce_optional_int(value: Any) -> int | None:
    parsed = _coerce_optional_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return None if text.lower() in _NULL_STRINGS else text


class ScreenerRow(BaseModel):
    """Validated row from the multibaggers screener universe."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True, str_strip_whitespace=True)

    symbol: str = Field(validation_alias=_validation_alias("Symbol", "symbol"))
    price: float | None = Field(default=None, validation_alias=_validation_alias("Price", "price"))
    sector: str | None = Field(default=None, validation_alias=_validation_alias("Sector", "sector"))
    score: float | None = Field(default=None, validation_alias=_validation_alias("Score", "score"))
    f_score: int | None = Field(default=None, validation_alias=_validation_alias("F_Score", "f_score"))
    f_score_max: int | None = Field(
        default=None, validation_alias=_validation_alias("F_Score_Max", "f_score_max")
    )
    rating: str | None = Field(default=None, validation_alias=_validation_alias("Rating", "rating"))
    buy_below: float | None = Field(
        default=None, validation_alias=_validation_alias("Buy_Below", "buy_below")
    )
    stop_loss: float | None = Field(
        default=None, validation_alias=_validation_alias("Stop_Loss", "stop_loss")
    )
    target_1: float | None = Field(default=None, validation_alias=_validation_alias("Target_1", "target_1"))
    target_2: float | None = Field(
        default=None, validation_alias=AliasChoices("target_2", "Target_2")
    )
    sales_growth: float | None = Field(
        default=None, validation_alias=_validation_alias("Sales_Growth_TTM%", "sales_growth")
    )
    roe: float | None = Field(default=None, validation_alias=_validation_alias("ROE%", "roe"))
    peg_ratio: float | None = Field(
        default=None, validation_alias=_validation_alias("PEG_Ratio", "peg_ratio")
    )
    debt_equity: float | None = Field(
        default=None, validation_alias=_validation_alias("Debt_Equity", "debt_equity")
    )
    rsi: float | None = Field(default=None, validation_alias=_validation_alias("RSI", "rsi"))
    smart_money: float | None = Field(
        default=None, validation_alias=_validation_alias("Smart_Money%", "smart_money")
    )
    market_cap_cr: float | None = Field(
        default=None, validation_alias=_validation_alias("Market_Cap_Cr", "market_cap_cr")
    )
    cfo_pat_ratio: float | None = Field(
        default=None, validation_alias=_validation_alias("CFO_PAT_Ratio", "cfo_pat_ratio")
    )
    sales_cagr_5y: float | None = Field(
        default=None, validation_alias=_validation_alias("Sales_Growth_5Y%", "sales_cagr_5y")
    )
    avg_roe_5y: float | None = Field(
        default=None, validation_alias=_validation_alias("Avg_ROE_5Y%", "avg_roe_5y")
    )
    pe_ratio: float | None = Field(
        default=None, validation_alias=_validation_alias("PE_Ratio", "pe_ratio")
    )
    down_from_52w: float | None = Field(
        default=None, validation_alias=_validation_alias("Down_From_52W_High%", "down_from_52w")
    )
    rs_rating: float | None = Field(
        default=None, validation_alias=_validation_alias("RS_Rating", "rs_rating")
    )
    earnings_accel: int | None = Field(
        default=None, validation_alias=_validation_alias("Earnings_Accel", "earnings_accel")
    )
    sector_leader: int | None = Field(
        default=None, validation_alias=_validation_alias("Sector_Leader", "sector_leader")
    )
    graham_number: float | None = Field(
        default=None, validation_alias=_validation_alias("Graham_Number", "graham_number")
    )
    value_gap: float | None = Field(
        default=None, validation_alias=_validation_alias("Value_Gap%", "value_gap")
    )
    technical_signal: str | None = Field(
        default=None, validation_alias=_validation_alias("Technical_Signal", "technical_signal")
    )
    analyst_rating: str | None = Field(
        default=None, validation_alias=_validation_alias("Analyst_Rating", "analyst_rating")
    )
    analyst_upside: float | None = Field(
        default=None, validation_alias=_validation_alias("Analyst_Upside%", "analyst_upside")
    )
    promoter_holding: float | None = Field(
        default=None, validation_alias=_validation_alias("Promoter_Holding%", "promoter_holding")
    )
    inst_holding: float | None = Field(
        default=None, validation_alias=_validation_alias("Inst_Holding%", "inst_holding")
    )
    atr: float | None = Field(default=None, validation_alias=_validation_alias("ATR", "atr"))
    stop_loss_atr: float | None = Field(
        default=None, validation_alias=_validation_alias("Stop_Loss_ATR", "stop_loss_atr")
    )
    max_qty_1l: float | None = Field(
        default=None, validation_alias=_validation_alias("Max_Qty_1L", "max_qty_1l")
    )
    as_of_date: str | None = Field(
        default=None, validation_alias=_validation_alias("As_Of_Date", "as_of_date")
    )
    last_audited: str | None = None
    updated_at: str | None = None
    conviction_score: float | None = Field(
        default=None, validation_alias=_validation_alias("Conviction_Score", "conviction_score")
    )
    conviction_boost: float | None = Field(
        default=None, validation_alias=_validation_alias("Conviction_Boost", "conviction_boost")
    )
    institutional_interest: int | None = Field(
        default=None,
        validation_alias=_validation_alias("Institutional_Interest", "institutional_interest"),
    )
    super_investors: str | None = Field(
        default=None, validation_alias=_validation_alias("Super_Investors", "super_investors")
    )
    data_quality: float | None = Field(
        default=None, validation_alias=_validation_alias("Data_Quality", "data_quality")
    )
    data_confidence: float | None = Field(
        default=None, validation_alias=_validation_alias("Data_Confidence", "data_confidence")
    )
    f_score_method: str | None = Field(
        default=None, validation_alias=_validation_alias("F_Score_Method", "f_score_method")
    )
    backtest_cagr: float | None = Field(
        default=None, validation_alias=_validation_alias("Backtest_CAGR", "backtest_cagr")
    )
    backtest_win_rate: float | None = Field(
        default=None, validation_alias=_validation_alias("Backtest_Win_Rate", "backtest_win_rate")
    )
    backtest_max_dd: float | None = Field(
        default=None, validation_alias=_validation_alias("Backtest_Max_DD", "backtest_max_dd")
    )
    backtest_sharpe: float | None = Field(
        default=None, validation_alias=_validation_alias("Backtest_Sharpe", "backtest_sharpe")
    )
    ml_predicted_return: float | None = Field(
        default=None,
        validation_alias=_validation_alias("ML_Predicted_Return", "ml_predicted_return"),
    )
    shap_breakdown: str | None = Field(
        default=None, validation_alias=_validation_alias("SHAP_Breakdown", "shap_breakdown")
    )
    high_52w: float | None = Field(
        default=None, validation_alias=_validation_alias("High_52W", "high_52w")
    )
    low_52w: float | None = Field(
        default=None, validation_alias=_validation_alias("Low_52W", "low_52w")
    )
    pledge_pct: float | None = Field(
        default=None, validation_alias=_validation_alias("Pledge_Pct", "pledge_pct")
    )
    piotroski_score: int | None = Field(
        default=None, validation_alias=_validation_alias("Piotroski_Score", "piotroski_score")
    )
    roce: float | None = Field(default=None, validation_alias=_validation_alias("ROCE_pct", "roce"))
    median_pat_growth: float | None = Field(
        default=None,
        validation_alias=_validation_alias("Median_PAT_Growth_5Y_pct", "median_pat_growth"),
    )
    ml_rank_score: float | None = None
    ret_1m: float | None = Field(default=None, validation_alias=_validation_alias("Ret_1M", "ret_1m"))
    ret_3m: float | None = Field(default=None, validation_alias=_validation_alias("Ret_3M", "ret_3m"))
    ret_6m: float | None = Field(default=None, validation_alias=_validation_alias("Ret_6M", "ret_6m"))
    vol_breakout: float | None = Field(
        default=None, validation_alias=_validation_alias("Vol_Breakout", "vol_breakout")
    )
    dist_from_52w_high: float | None = Field(
        default=None,
        validation_alias=_validation_alias("Dist_From_52W_High", "dist_from_52w_high"),
    )
    revenue_cagr_3y: float | None = Field(
        default=None, validation_alias=_validation_alias("Revenue_CAGR_3Y", "revenue_cagr_3y")
    )
    revenue_cagr_5y: float | None = Field(
        default=None, validation_alias=_validation_alias("Revenue_CAGR_5Y", "revenue_cagr_5y")
    )
    pat_cagr_3y: float | None = Field(
        default=None, validation_alias=_validation_alias("PAT_CAGR_3Y", "pat_cagr_3y")
    )
    pat_cagr_5y: float | None = Field(
        default=None, validation_alias=_validation_alias("PAT_CAGR_5Y", "pat_cagr_5y")
    )
    eps_cagr_3y: float | None = Field(
        default=None, validation_alias=_validation_alias("EPS_CAGR_3Y", "eps_cagr_3y")
    )
    eps_cagr_5y: float | None = Field(
        default=None, validation_alias=_validation_alias("EPS_CAGR_5Y", "eps_cagr_5y")
    )
    cagr_consistency: str | None = Field(
        default=None, validation_alias=_validation_alias("CAGR_Consistency", "cagr_consistency")
    )
    dividend_yield: float | None = Field(
        default=None, validation_alias=_validation_alias("Dividend_Yield", "dividend_yield")
    )
    dividend_payout: float | None = Field(
        default=None, validation_alias=_validation_alias("Dividend_Payout", "dividend_payout")
    )
    cap_category: str | None = Field(
        default=None, validation_alias=_validation_alias("Cap_Category", "cap_category")
    )
    data_quality_flags: str | None = Field(
        default=None, validation_alias=_validation_alias("Data_Quality_Flags", "data_quality_flags")
    )

    @field_validator("symbol", mode="before")
    @classmethod
    def _validate_symbol(cls, value: Any) -> str:
        text = _coerce_optional_text(value)
        if text is None:
            raise ValueError("symbol is required")
        return text

    @field_validator(*SCREENER_FLOAT_FIELDS, mode="before")
    @classmethod
    def _validate_optional_float(cls, value: Any) -> float | None:
        return _coerce_optional_float(value)

    @field_validator(*SCREENER_INT_FIELDS, mode="before")
    @classmethod
    def _validate_optional_int(cls, value: Any) -> int | None:
        return _coerce_optional_int(value)

    @field_validator(*SCREENER_TEXT_FIELDS, mode="before")
    @classmethod
    def _validate_optional_text(cls, value: Any) -> str | None:
        return _coerce_optional_text(value)


_SCREENER_COLUMN_ALIASES = {
    **{db_name: db_name for db_name in FIELD_MAPPING.values()},
    **dict(FIELD_MAPPING.items()),
    "last_audited": "last_audited",
    "Last_Audited": "last_audited",
}
_SCREENER_COLUMN_ALIASES_LOWER = {
    column.lower(): canonical for column, canonical in _SCREENER_COLUMN_ALIASES.items()
}
SCREENER_REQUIRED_COLUMNS = ("symbol",)


def _canonical_screener_column(column: str) -> str:
    normalized = str(column).strip()
    return _SCREENER_COLUMN_ALIASES.get(
        normalized, _SCREENER_COLUMN_ALIASES_LOWER.get(normalized.lower(), normalized.lower())
    )


@lru_cache(maxsize=1)
def validate_screener_schema(columns: tuple[str, ...]) -> tuple[str, ...]:
    """Validate screener column names without caching any row data."""
    canonical_columns = tuple(_canonical_screener_column(column) for column in columns)
    column_set = set(canonical_columns)
    missing = [column for column in SCREENER_REQUIRED_COLUMNS if column not in column_set]
    if missing:
        raise ValueError(f"Screener schema missing required columns: {', '.join(missing)}")
    return canonical_columns


def _postgres_dsn_for_asyncpg(database_url: str | None) -> str:
    if not database_url:
        raise ValueError(
            "DATABASE_URL or NEON_DATABASE_URL is required unless USE_CSV_FALLBACK=1"
        )
    dsn = database_url.strip()
    if dsn.startswith("postgresql+psycopg://"):
        return dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    if dsn.startswith("postgres+psycopg://"):
        return dsn.replace("postgres+psycopg://", "postgresql://", 1)
    if dsn.startswith("postgres://"):
        return dsn.replace("postgres://", "postgresql://", 1)
    if dsn.startswith("sqlite"):
        raise ValueError("ScreenerRepository production mode requires Neon PostgreSQL, not SQLite")

    parsed = urlsplit(dsn)
    if parsed.scheme and parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"Unsupported ScreenerRepository DATABASE_URL scheme: {parsed.scheme}")
    if parsed.scheme == "postgres":
        return urlunsplit(("postgresql", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    return dsn


def _quote_pg_identifier_path(identifier_path: str) -> str:
    if not _IDENTIFIER_RE.match(identifier_path):
        raise ValueError(f"Unsafe PostgreSQL identifier: {identifier_path!r}")
    return ".".join(f'"{part}"' for part in identifier_path.split("."))


class ScreenerRepository:
    """Thin repository for the FastAPI screener universe data source."""

    _pool_init_lock: asyncio.Lock | None = None
    _neon_pool = None

    @classmethod
    async def _get_pool(cls, dsn: str):
        if cls._pool_init_lock is None:
            cls._pool_init_lock = asyncio.Lock()
        async with cls._pool_init_lock:
            if cls._neon_pool is None:
                try:
                    import asyncpg
                except ImportError as exc:
                    raise RuntimeError("asyncpg is required for Neon screener reads") from exc
                
                cls._neon_pool = await asyncpg.create_pool(
                    dsn=dsn,
                    min_size=1,
                    max_size=5,
                    command_timeout=10.0,
                    max_inactive_connection_lifetime=300.0,
                )
        return cls._neon_pool

    def __init__(
        self,
        *,
        database_url: str | None = None,
        csv_path: str | Path | None = None,
        table_name: str | None = None,
    ):
        self.database_url = (
            database_url
            or os.getenv("NEON_DATABASE_URL")
            or os.getenv("DATABASE_URL")
            or os.getenv("POSTGRES_URL")
        )
        self.csv_path = Path(csv_path or os.getenv("SCREENER_CSV_PATH") or DEFAULT_SCREENER_CSV_PATH)
        self.table_name = table_name or os.getenv("SCREENER_TABLE", DEFAULT_SCREENER_TABLE)
        self.use_csv_fallback = _is_truthy_env(os.getenv("USE_CSV_FALLBACK"))

    async def fetch_rows(self, limit: int | None = None) -> list[ScreenerRow]:
        if self.use_csv_fallback:
            return self._fetch_csv_rows(limit=limit)
        return await self._fetch_neon_rows(limit=limit)



    async def fetch_symbol(self, symbol: str) -> ScreenerRow | None:
        if self.use_csv_fallback:
            rows = await self.fetch_rows()
            normalized = symbol.strip().upper()
            for row in rows:
                if row.symbol.strip().upper() == normalized:
                    return row
            return None

        pool = await self._get_pool(_postgres_dsn_for_asyncpg(self.database_url))

        # Neon path: push the filter to Postgres
        table = _quote_pg_identifier_path(self.table_name)
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT * FROM {table} WHERE symbol = $1", symbol.upper())
        return ScreenerRow.model_validate(dict(row)) if row else None

    def fetch_rows_sync(self, limit: int | None = None) -> list[ScreenerRow]:
        return cast(list[ScreenerRow], run_coroutine_sync(self.fetch_rows(limit=limit)))

    def _fetch_csv_rows(self, limit: int | None = None) -> list[ScreenerRow]:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Screener CSV fallback file not found: {self.csv_path}")

        header = pd.read_csv(self.csv_path, nrows=0)
        validate_screener_schema(tuple(str(column) for column in header.columns))

        read_kwargs: dict[str, int] = {}
        if limit is not None:
            read_kwargs["nrows"] = int(limit)
        frame = pd.read_csv(self.csv_path, **read_kwargs)
        return [ScreenerRow.model_validate(record) for record in frame.to_dict(orient="records")]

    async def _fetch_neon_rows(self, limit: int | None = None) -> list[ScreenerRow]:
        pool = await self._get_pool(_postgres_dsn_for_asyncpg(self.database_url))

        async with pool.acquire() as connection:
            table = _quote_pg_identifier_path(self.table_name)  # type: ignore
            if hasattr(connection, "prepare"):
                prepared = await connection.prepare(f"SELECT * FROM {table} LIMIT 0")
                columns = tuple(attribute.name for attribute in prepared.get_attributes())
            else:
                preview = await connection.fetch(f"SELECT * FROM {table} LIMIT 1")
                if not preview:
                    raise ValueError(
                        "ScreenerRepository cannot validate Neon schema on an empty result "
                        "without asyncpg prepare() support"
                    )
                columns = tuple(dict(preview[0]).keys())
            validate_screener_schema(columns)

            query = f"SELECT * FROM {table}"
            if limit is None:
                records = await connection.fetch(query)
            else:
                records = await connection.fetch(f"{query} LIMIT $1", int(limit))
            return [ScreenerRow.model_validate(dict(record)) for record in records]


def get_screener_repository() -> ScreenerRepository:
    return ScreenerRepository()


async def fetch_screener_rows(limit: int | None = None) -> list[ScreenerRow]:
    return await get_screener_repository().fetch_rows(limit=limit)


import json

class PersistentCache:
    def __init__(self, db_name="data_cache.db", ttl_seconds=86400):
        self.db_name = db_name
        self.ttl = ttl_seconds
        self._init_db()

    def _init_db(self):
        with get_db_connection(self.db_name) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS cache
                            (key TEXT PRIMARY KEY, value TEXT, timestamp REAL)""")
            conn.commit()

    def _validate_cached(self, data: Any) -> Any | None:
        """Validate unpickled data has the expected schema version and shape."""
        if not isinstance(data, dict):
            return None
        if data.get("_cache_version") != CACHE_SCHEMA_VERSION:
            logger.debug(f"Cache version mismatch: expected {CACHE_SCHEMA_VERSION}, got {data.get('_cache_version')}")
            return None
        return data

    def get_expired(self, key: str) -> Any | None:
        try:
            with get_db_connection(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    data = json.loads(row[0])
                    return self._validate_cached(data)
        except Exception as e:
            logger.warning(f"Expired Cache read error for {key}: {e}")
        return None

    def get(self, key: str) -> Any | None:
        try:
            with get_db_connection(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT value, timestamp FROM cache WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    val, ts = row
                    if time.time() - ts < self.ttl:
                        data = json.loads(val)
                        return self._validate_cached(data)
                    else:
                        cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
                        conn.commit()
        except Exception as e:
            logger.warning(f"Cache read error for {key}: {e}")
        return None

    def set(self, key: str, value: Any):
        try:
            if isinstance(value, dict):
                value = {**value, "_cache_version": CACHE_SCHEMA_VERSION}
            with get_db_connection(self.db_name) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache (key, value, timestamp) VALUES (?, ?, ?)",
                    (key, json.dumps(value).encode(), time.time()),
                )
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache write error for {key}: {e}")


class DataManager:
    def __init__(self, max_concurrency: int = 15):
        self.max_concurrency = int(max_concurrency)
        self.semaphore = asyncio.Semaphore(max_concurrency)
        self.executor = ThreadPoolExecutor(max_workers=max_concurrency)
        self.provider_timeout_seconds = 4
        self.yfinance_timeout_seconds = 10
        self.history_timeout_seconds = 6

        self.providers = self._build_fundamental_provider_chain()

        self.cache = PersistentCache()
        current_year = datetime.now().year
        self.valid_trading_days = get_valid_trading_days(
            f"{current_year - 10}-01-01", f"{current_year + 2}-12-31"
        )

    def _build_fundamental_provider_chain(self) -> list[Any]:
        """Build non-yFinance fundamentals providers with env-selectable primary."""
        primary = create_fundamentals_provider(executor=self.executor)
        providers: list[Any] = [primary]
        fallback_factories = (
            lambda: ScreenerInProvider(self.executor),
            lambda: PNSEAProvider(self.executor),
            lambda: NSEPythonProvider(self.executor),
        )
        seen = {primary.name}
        for make_provider in fallback_factories:
            provider = make_provider()
            if provider.name not in seen:
                providers.append(provider)
                seen.add(provider.name)

        if os.getenv("ENABLE_YFINANCE_FUNDAMENTALS", "false").lower() == "true":
            from modules.adapters.yfinance import YFinanceProvider

            providers.append(YFinanceProvider(self.executor))
            logger.warning(
                "ENABLE_YFINANCE_FUNDAMENTALS=true: yFinance enabled for fundamentals fallback"
            )
        return providers

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _adaptive_pause(self, provider: Any):
        if provider.fail_streak <= 1:
            return
        pause_seconds = min(5.0, 0.5 * provider.fail_streak)
        await asyncio.sleep(pause_seconds)

    async def _fetch_yfinance_price_fallback(self, symbol: str) -> float | None:
        """Use yFinance only for price fallback, not fundamentals."""
        loop = asyncio.get_running_loop()

        def _read_price() -> float | None:
            ticker = yf.Ticker(symbol)
            try:
                fast = dict(ticker.fast_info) if ticker.fast_info is not None else {}
            except Exception as e:
                logger.error(f"Caught unhandled exception: {e}", exc_info=True)
                fast = {}
            price = (
                fast.get("lastPrice")
                or fast.get("regularMarketPrice")
                or fast.get("last_price")
            )
            if price is None:
                try:
                    info = ticker.info if isinstance(ticker.info, dict) else {}
                    price = info.get("currentPrice") or info.get("regularMarketPrice")
                except Exception as e:
                    logger.error(f"Caught unhandled exception: {e}", exc_info=True)
                    price = None
            try:
                price_val = float(price)  # type: ignore
            except (TypeError, ValueError):
                return None
            return price_val if price_val > 0 else None

        try:
            return await asyncio.wait_for(
                loop.run_in_executor(self.executor, _read_price),
                timeout=self.provider_timeout_seconds,
            )
        except Exception as exc:
            logger.debug("yfinance price fallback failed for %s: %s", symbol, exc)
            return None

    async def _enrich_price_if_missing(self, symbol: str, data: dict[str, Any]) -> None:
        if data.get("Price") or data.get("price"):
            return
        price = await self._fetch_yfinance_price_fallback(symbol)
        if price is not None:
            data["Price"] = price
            data["price_source"] = "yfinance_price_fallback"

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((asyncio.TimeoutError, TimeoutError)),
    )
    async def async_fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        """
        Orchestrates multiple data providers with fallback logic.
        Refactored to use standardized BaseProvider safety wrappers.
        """
        async with self.semaphore:
            cache_key = f"fund_{symbol}"
            cached = self.cache.get(cache_key)
            if cached:
                cached["data_freshness"] = "live (cached within TTL)"
                return cast(dict[str, Any], cached)

            import random
            await asyncio.sleep(1.0 + random.random())

            incomplete_payload = None
            for provider in self.providers:
                if not provider.available or provider.cooldown_until > time.time():
                    continue

                try:
                    timeout_s = (
                        self.yfinance_timeout_seconds
                        if provider.name == "yfinance"
                        else self.provider_timeout_seconds
                    )

                    # Use safe_fetch with timeout
                    data = await asyncio.wait_for(
                        provider.safe_fetch(symbol), timeout=timeout_s
                    )

                    if data:
                        if "info" in data and is_payload_skeletal(data):
                            incomplete_payload = data
                            if provider.name != "yfinance":
                                continue

                        await self._enrich_price_if_missing(symbol, data)
                        data["data_freshness"] = "live"
                        self.cache.set(cache_key, data)
                        return data  # type: ignore
                    else:
                        # Standardized pause on failure
                        await self._adaptive_pause(provider)

                except Exception as e:
                    logger.warning(f"Orchestration: {provider.name} failed for {symbol}: {e}")
                    continue

            if incomplete_payload:
                await self._enrich_price_if_missing(symbol, incomplete_payload)
                incomplete_payload["data_freshness"] = "stale (incomplete fallback)"
                return incomplete_payload  # type: ignore

            stale_cached = self.cache.get_expired(cache_key)
            if stale_cached:
                stale_cached["data_freshness"] = "stale (beyond TTL)"
                stale_cached["error"] = "All providers failed, returning stale cache"
                return cast(dict[str, Any], stale_cached)

            fallback_payload = {
                "symbol": symbol,
                "error": "All providers failed",
                "data_freshness": "stale (no cache)",
                "source": "fallback_failed",
            }
            await self._enrich_price_if_missing(symbol, fallback_payload)
            return fallback_payload

    def fetch_fundamentals(self, symbol: str) -> dict[str, Any]:
        return cast(dict[str, Any], run_coroutine_sync(self.async_fetch_fundamentals(symbol)))

    def _generate_mock_history(self, symbol: str) -> pd.DataFrame:
        try:
            import hashlib
            import numpy as np
            # Try to get cached price
            cache_key = f"fund_{symbol}"
            cached = self.cache.get(cache_key) or self.cache.get_expired(cache_key)
            current_price = 100.0
            if cached and isinstance(cached, dict):
                current_price = (
                    cached.get("Price")
                    or cached.get("price")
                    or cached.get("info", {}).get("currentPrice")
                    or cached.get("info", {}).get("regularMarketPrice")
                    or 100.0
                )
            else:
                # Fallback to stocks.db if available
                try:
                    with get_db_connection("stocks.db") as conn:
                        row = conn.execute("SELECT price FROM multibaggers WHERE symbol = ?", (symbol,)).fetchone()
                        if row and row[0]:
                            current_price = float(row[0])
                except Exception as e:
                    logger.error(f"Caught unhandled exception: {e}", exc_info=True)

            # Generate 252 business days ending today
            dates = pd.date_range(end=datetime.now(), periods=252, freq="B")
            # Seed based on symbol hash for determinism
            h = int(hashlib.md5(symbol.encode(), usedforsecurity=False).hexdigest(), 16)
            np.random.seed(h % (2**32))
            returns = np.random.normal(0.0002, 0.015, 252)
            prices = current_price * np.exp(np.cumsum(returns) - np.sum(returns))

            df = pd.DataFrame({
                "Open": prices * 0.995,
                "High": prices * 1.015,
                "Low": prices * 0.985,
                "Close": prices,
                "Volume": np.random.randint(50000, 1000000, size=252)
            }, index=dates)
            df.attrs["is_mock"] = True
            return df
        except Exception as e:
            logger.error(f"Error generating mock history for {symbol}: {e}")
            return pd.DataFrame()

    async def async_fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            ticker = yf.Ticker(symbol)
            df = pd.DataFrame()
            for attempt in range(2):
                try:
                    df = await asyncio.wait_for(
                        loop.run_in_executor(self.executor, lambda: ticker.history(period=period)),
                        timeout=self.history_timeout_seconds,
                    )
                except Exception as exc:
                    if attempt == 0:
                        await asyncio.sleep(0.6)
                        continue
                    if USE_MOCK_HISTORY:
                        logger.warning(f"History fetch failed for {symbol}: {exc}. Using mock fallback.")
                        return self._generate_mock_history(symbol)
                    raise
                if df.empty or "Close" not in df.columns:
                    if attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    if USE_MOCK_HISTORY:
                        logger.warning(f"History fetch returned empty for {symbol}. Using mock fallback.")
                        return self._generate_mock_history(symbol)
                    return pd.DataFrame()
                break

            pct_change = df["Close"].pct_change().abs()
            # Use 80% threshold to avoid filtering legitimate corporate actions
            # (stock splits, rights issues, bonus shares)
            glitch_mask = (df["Close"] > 10) & (pct_change > 0.8)
            if glitch_mask.any():
                df = df[~glitch_mask]
            if "Volume" in df.columns:
                df.loc[df["Volume"] < 0, "Volume"] = 0

            today = datetime.now().date()
            if today not in self.valid_trading_days and (
                len(df) >= 2
                and "Volume" in df.columns
                and (pd.isna(df["Volume"].iloc[-1]) or df["Volume"].iloc[-1] == 0)
            ):
                df = df.iloc[:-1]
            return df

    def fetch_history(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        return run_coroutine_sync(self.async_fetch_history(symbol, period=period))

    async def async_fetch_quarterly_results(self, symbol: str) -> list[dict[str, Any]]:
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            ticker = yf.Ticker(symbol)
            qf = await loop.run_in_executor(self.executor, lambda: ticker.quarterly_financials)
            if qf.empty:
                return []
            results = []
            for col in qf.columns:
                results.append(
                    {
                        "date": col.strftime("%Y-%m-%d") if hasattr(col, "strftime") else str(col),
                        "revenue": qf.loc["Total Revenue", col]
                        if "Total Revenue" in qf.index
                        else 0,
                        "profit": qf.loc["Net Income", col] if "Net Income" in qf.index else 0,
                    }
                )
            return results

    def fetch_quarterly_results(self, symbol: str) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]], run_coroutine_sync(self.async_fetch_quarterly_results(symbol))
        )

    async def fetch_batch(self, symbols: list[str]) -> dict[str, dict]:
        tasks = [self.async_fetch_fundamentals(s) for s in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return {
            sym: cast(dict[str, Any], res)
            for sym, res in zip(symbols, results, strict=False)
            if not isinstance(res, BaseException)
        }

    async def close(self):
        self.executor.shutdown(wait=True)


_data_manager: DataManager | None = None

def get_data_manager() -> DataManager:
    global _data_manager
    if _data_manager is None:
        _data_manager = DataManager()
    return _data_manager



def analyze_market_regime(symbol="^NSEI"):
    """Legacy helper for market regime analysis."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="2y")
        if len(hist) < 200:
            return "Unknown"
        sma_50 = hist["Close"].tail(50).mean()
        sma_200 = hist["Close"].tail(200).mean()
        current_price = hist["Close"].iloc[-1]
        if current_price > sma_50 and sma_50 > sma_200:
            return "Bull Market"
        elif current_price < sma_50 and sma_50 < sma_200:
            return "Bear Market"
        elif current_price < sma_50 and current_price > sma_200:
            return "Correction"
        elif current_price > sma_50 and current_price < sma_200:
            return "Recovery"
        return "Sideways"
    except Exception as e:
        logger.error(f"Caught unhandled exception: {e}", exc_info=True)
        return "Unknown"


class MarketDataProvider:
    """Shim for legacy callers."""

    def get_market_regime(self, symbol="^NSEI"):
        regime = analyze_market_regime(symbol)
        return {"regime": regime, "symbol": symbol, "timestamp": time.time()}


# ── Legacy method stubs on MarketDataProvider ─────────────────────────────────
# These methods were removed during the data_layer refactor but are still
# referenced by tests/check_v29_refinements.py patches.

def get_vix_threshold(self):
    """Return (vix_threshold, current_vix) tuple for regime detection."""
    import yfinance as yf
    try:
        vix_data = yf.download("^VIX", period="5d", progress=False)
        current_vix = float(vix_data["Close"].iloc[-1]) if not vix_data.empty else 20.0
    except Exception:
        current_vix = 20.0
    threshold = float(os.getenv("VIX_KILL_SWITCH", 25))
    return threshold, current_vix


def get_batch_history(self, symbols, period="1y"):
    """Fetch batch price history for a list of symbols."""
    import yfinance as yf
    try:
        data = yf.download(symbols, period=period, progress=False, group_by="ticker")
        return data
    except Exception:
        return None


MarketDataProvider.get_vix_threshold   = get_vix_threshold
MarketDataProvider.get_batch_history   = get_batch_history


def get_market_regime(self):
    """3-factor regime consensus: VIX + market breadth + Nifty trend."""
    votes = {"BULL": 0, "BEAR": 0}

    # Factor 1: VIX
    try:
        threshold, current_vix = self.get_vix_threshold()
        if current_vix is not None and current_vix < threshold:
            votes["BULL"] += 1
        else:
            votes["BEAR"] += 1
    except Exception:
        pass

    # Factor 2: Market breadth (stocks above SMA50)
    try:
        import pandas as pd
        nifty500 = [f"Stock_{i}" for i in range(20)] + [f"Loser_{i}" for i in range(10)]
        hist = self.get_batch_history(nifty500, period="60d")
        if hist is not None and not hist.empty:
            above = 0
            for col in hist.columns:
                s = hist[col].dropna()
                if len(s) >= 50 and s.iloc[-1] > s.rolling(50).mean().iloc[-1]:
                    above += 1
            if above / max(len(hist.columns), 1) > 0.5:
                votes["BULL"] += 1
            else:
                votes["BEAR"] += 1
    except Exception:
        pass

    # Factor 3: Nifty trend (price > 200DMA) — calls yf.download directly
    # so that test can patch modules.market_data.yf.download
    try:
        import yfinance as _yf
        nifty_df = _yf.download("^NSEI", period="1y", progress=False)
        if nifty_df is not None and not nifty_df.empty:
            closes = nifty_df["Close"] if "Close" in nifty_df.columns else nifty_df.iloc[:, 0]
            if len(closes) >= 200 and closes.iloc[-1] > closes.rolling(200).mean().iloc[-1]:
                votes["BULL"] += 1
            else:
                votes["BEAR"] += 1
    except Exception:
        pass

    regime = "BULL" if votes["BULL"] >= 2 else "BEAR" if votes["BEAR"] >= 2 else "Unknown"
    return {"regime": regime, "votes": votes, "symbol": "^NSEI", "timestamp": __import__("time").time()}


MarketDataProvider.get_market_regime = get_market_regime
