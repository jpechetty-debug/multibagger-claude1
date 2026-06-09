# ── Append to db/models.py ────────────────────────────────────────────────────
#
# 1. On the existing Multibagger class, add ONE line inside the class body:
#
#       shap_top_drivers = Column(Text)   # JSON list of top-5 SHAP drivers
#
#    Place it directly after the existing:
#       shap_breakdown = Column(Text)
#
#
# 2. Paste the full MlMetadata class below at the bottom of db/models.py.


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
