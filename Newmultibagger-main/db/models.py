# db/models.py
"""
SQLAlchemy 2.0 ORM Models — Sovereign AI Trading Engine v4.0
Mirrors the existing SQLite schema for seamless PostgreSQL/TimescaleDB migration.
"""

from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Multibagger(Base):
    __tablename__ = "multibaggers"

    symbol = Column(String, primary_key=True)
    price = Column(Float)
    sector = Column(String)
    score = Column(Integer)
    f_score = Column(Integer)
    f_score_max = Column(Integer)
    rating = Column(String)
    buy_below = Column(Float)
    stop_loss = Column(Float)
    target_1 = Column(Float)
    target_2 = Column(Float)
    sales_growth = Column(Float)
    roe = Column(Float)
    peg_ratio = Column(Float)
    debt_equity = Column(Float)
    rsi = Column(Float)
    smart_money = Column(Float)
    market_cap_cr = Column(Float)
    cfo_pat_ratio = Column(Float)
    sales_cagr_5y = Column(Float)
    avg_roe_5y = Column(Float)
    pe_ratio = Column(Float)
    down_from_52w = Column(Float)
    rs_rating = Column(Float)
    earnings_accel = Column(Integer)
    sector_leader = Column(Integer)
    graham_number = Column(Float)
    value_gap = Column(Float)
    technical_signal = Column(String)
    analyst_rating = Column(String)
    analyst_upside = Column(Float)
    promoter_holding = Column(Float)
    inst_holding = Column(Float)
    atr = Column(Float)
    stop_loss_atr = Column(Float)
    max_qty_1l = Column(Float)
    as_of_date = Column(Date)
    last_audited = Column(DateTime)
    updated_at = Column(DateTime)
    conviction_score = Column(Float)
    conviction_boost = Column(Float)
    institutional_interest = Column(Integer)
    super_investors = Column(Text)
    data_quality = Column(Float)
    data_confidence = Column(Float)
    f_score_method = Column(String)
    backtest_cagr = Column(Float)
    backtest_win_rate = Column(Float)
    backtest_max_dd = Column(Float)
    backtest_sharpe = Column(Float)
    ml_predicted_return = Column(Float)
    shap_breakdown = Column(Text)
    shap_top_drivers = Column(Text)
    
    # Phase 1: New Alpha Data
    ocf_yield = Column(Float)
    earnings_velocity_qoq = Column(Float)
    earnings_velocity_yoy = Column(Float)

    __table_args__ = (
        CheckConstraint("pe_ratio >= -100 AND pe_ratio <= 1000"),
        CheckConstraint("roe >= -500 AND roe <= 500"),
        CheckConstraint("score >= 0 AND score <= 100"),
    )


class FundamentalsPIT(Base):
    __tablename__ = "fundamentals_pit"

    symbol = Column(String, primary_key=True)
    as_of_date = Column(Date, primary_key=True, nullable=False)
    price = Column(Float)
    sector = Column(String)
    score = Column(Integer)
    sales_cagr_5y = Column(Float)
    avg_roe_5y = Column(Float)
    pe_ratio = Column(Float)
    debt_equity = Column(Float)
    market_cap_cr = Column(Float)
    cfo_pat_ratio = Column(Float)
    
    # Phase 1: New Alpha Data
    ocf_yield = Column(Float)
    earnings_velocity_qoq = Column(Float)
    earnings_velocity_yoy = Column(Float)

    source_updated_at = Column(DateTime)
    created_at = Column(DateTime, default=_utc_now)

    __table_args__ = (Index("idx_fundamentals_pit_as_of_date", "as_of_date"),)


class InstitutionalFlow(Base):
    """Phase 1: Base table for SEBI SAST and Block Deals."""

    __tablename__ = "institutional_flows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    execution_date = Column(Date, nullable=False)
    transaction_type = Column(String)   # e.g., 'SAST', 'BLOCK', 'BULK'
    party_name = Column(String)
    quantity = Column(Float)
    price_per_share = Column(Float)
    value_cr = Column(Float)
    reported_at = Column(DateTime, default=_utc_now)

    __table_args__ = (
        Index("idx_inst_flows_sym_date", "symbol", "execution_date"),
    )


class ScoreHistory(Base):
    __tablename__ = "score_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey("multibaggers.symbol"))
    timestamp = Column(DateTime, default=_utc_now)
    total_score = Column(Float)
    close_price = Column(Float)
    pe_ratio = Column(Float)


class FactorPenalty(Base):
    __tablename__ = "factor_penalties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, ForeignKey("multibaggers.symbol"))
    timestamp = Column(DateTime, default=_utc_now)
    penalty_name = Column(String)
    penalty_value = Column(Float)


class ValuationMetric(Base):
    __tablename__ = "valuation_metrics"

    symbol = Column(String, ForeignKey("multibaggers.symbol"), primary_key=True)
    dcf_value = Column(Float)
    graham_value = Column(Float)
    epv_value = Column(Float)
    intrinsic_value = Column(Float)
    margin_of_safety = Column(Float)
    verdict = Column(String)
    confidence_score = Column(Integer)
    as_of_date = Column(Date)
    calculated_at = Column(DateTime)


class Microcap(Base):
    __tablename__ = "microcaps"

    symbol = Column(String, primary_key=True)
    price = Column(Float)
    score = Column(Integer)
    market_cap = Column(Float)
    sales_growth = Column(Float)
    promoter_holding = Column(Float)
    buy_zone = Column(String)
    stop_loss = Column(Float)
    target_1 = Column(Float)
    target_2 = Column(Float)
    updated_at = Column(DateTime)


class Execution(Base):
    __tablename__ = "executions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String)
    side = Column(String)
    expected_price = Column(Float)
    fill_price = Column(Float)
    slippage_bps = Column(Float)
    liquidity_tier = Column(String)
    regime = Column(String)
    vix = Column(Float)
    timestamp = Column(DateTime)
    source = Column(String)


class SlippageMetric(Base):
    __tablename__ = "slippage_metrics"

    tier = Column(String, primary_key=True)
    time_window = Column(String, primary_key=True)
    regime = Column(String, primary_key=True)
    p50_bps = Column(Float)
    p75_bps = Column(Float)
    p95_bps = Column(Float)
    count = Column(Integer)
    updated_at = Column(DateTime)


class BuyThesis(Base):
    __tablename__ = "buy_thesis"

    symbol = Column(String, primary_key=True)
    buy_date = Column(String)
    primary_driver = Column(String)
    revenue_growth_min = Column(Float)
    operating_margin_min = Column(Float)
    score_at_buy = Column(Float)
    checklist_passes_at_buy = Column(Integer)
    regime_at_buy = Column(String)
    raw_thesis_json = Column(Text)
    created_at = Column(DateTime, default=_utc_now)


class DqSectorLimit(Base):
    """Per-sector metric limit overrides for data quality gates.

    Rows in this table override the flat METRIC_LIMITS in dq_gates.py
    for the given (sector, metric) pair. Metrics not present here
    fall back to the global defaults.
    """

    __tablename__ = "dq_sector_limits"

    sector = Column(String, primary_key=True)
    metric = Column(String, primary_key=True)
    min_val = Column(Float, nullable=False)
    max_val = Column(Float, nullable=False)
    auto_scale_threshold = Column(Float, nullable=True)


class HoldoutResult(Base):
    """Persists holdout evaluation metrics for overfitting detection."""

    __tablename__ = "holdout_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    evaluated_at = Column(DateTime, default=_utc_now)
    holdout_start = Column(String)
    holdout_end = Column(String)
    oos_r2 = Column(Float)
    spearman_ic = Column(Float)
    hit_rate = Column(Float)
    holdout_sharpe = Column(Float)
    wf_sharpe = Column(Float)
    sharpe_gap = Column(Float)
    overfitting_flag = Column(Integer, default=0)


class WebhookSubscription(Base):
    """One row per registered outbound webhook endpoint."""

    __tablename__ = "webhook_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(120), nullable=False)
    url = Column(Text, nullable=False)
    # 64-char hex HMAC secret — generated server-side, shown to caller once.
    secret = Column(String(64), nullable=False)
    # Comma-separated alert types; NULL = all.
    event_filter = Column(Text, nullable=True)
    is_active = Column(Integer, nullable=False, default=1)
    max_failures = Column(Integer, nullable=False, default=5)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=_utc_now, nullable=False)
    updated_at = Column(DateTime, default=_utc_now, onupdate=_utc_now, nullable=False)


class AlertDispatchLog(Base):
    """Append-only delivery log — every dispatch attempt writes a row."""

    __tablename__ = "alert_dispatch_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(
        Integer,
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    payload = Column(Text, nullable=False)          # full JSON we sent
    http_status = Column(Integer, nullable=True)    # NULL on network error
    # 'delivered' | 'failed' | 'pending'
    status = Column(String(16), nullable=False, default="pending")
    error_detail = Column(Text, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime, nullable=True)
    dispatched_at = Column(DateTime, nullable=False, default=_utc_now)

    __table_args__ = (
        Index("idx_adl_pending_retry", "status", "next_retry_at"),
        Index("idx_adl_subscription", "subscription_id", "dispatched_at"),
    )


class MlMetadata(Base):
    """One row per ML training run — persists walk-forward metrics and
    record counts so ml_ops.check_retraining_trigger can compare
    current PIT rows vs. the count seen at last training.

    This table was previously created by ml_ops.initialize_ml_metadata()
    at runtime, meaning a fresh `alembic upgrade head` deployment was
    missing it until the first /api/ml/train call.  Moving it here makes
    it part of the canonical schema.
    """

    __tablename__ = "ml_metadata"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    trained_at   = Column(DateTime, default=_utc_now)
    record_count = Column(Integer)
    r2_score     = Column(Float)
    spearman_ic  = Column(Float)
    hit_rate     = Column(Float)
    oos_r2       = Column(Float)
    wf_folds     = Column(Integer)
    model_path   = Column(Text)
