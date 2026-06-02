# config.py
# Global Configuration State
import os

from dotenv import load_dotenv

load_dotenv()

# ── SECURITY: Never use a fallback for API keys. ─────────────────────────────
# If the key is missing the engine must refuse to start rather than silently
# use a committed credential.
# ── SECURITY: Never use fallbacks for authentication tokens. ──────────────────
# Default config state — yfinance prioritized by default.

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production, set CORS_ALLOWED_ORIGINS to a comma-separated list.
# Default is localhost only — never use "*" in production.
_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:9005")
CORS_ALLOWED_ORIGINS: list[str] = [o.strip() for o in _cors_env.split(",") if o.strip()]

# ── Ollama / LLM ──────────────────────────────────────────────────────────────
OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b-instruct-fp16")

# ── Manual Regime Override ────────────────────────────────────────────────────
# Options: 'BULL', 'BEAR', 'SIDEWAYS', or None (Auto-Pilot)
FORCED_REGIME = os.getenv("FORCED_REGIME") or None

# ── System Settings ───────────────────────────────────────────────────────────
VERSION = "v4.2.0"
CAPITAL_LIMIT = 50_000_000  # 5 Cr pilot limit

# ── Model Integrity ───────────────────────────────────────────────────────────
MODEL_VERSION = VERSION

_git_hash_cache: str | None = None


def get_git_hash() -> str:
    """Lazy git hash — resolved on first call, never at import time.

    Priority: GIT_COMMIT_SHA env var → ``git rev-parse`` → "unknown".
    """
    global _git_hash_cache
    if _git_hash_cache is None:
        env_hash = os.getenv("GIT_COMMIT_SHA")
        if env_hash:
            _git_hash_cache = env_hash[:8]
        else:
            try:
                import subprocess

                _git_hash_cache = (
                    subprocess.check_output(
                        ["git", "rev-parse", "--short", "HEAD"],
                        stderr=subprocess.DEVNULL,
                    )
                    .decode("utf-8")
                    .strip()
                )
            except Exception:
                _git_hash_cache = "unknown"
    return _git_hash_cache


# Backward compat — consumers should migrate to get_git_hash()
MODEL_VERSION_HASH = "deferred"

# ── Risk Limits ───────────────────────────────────────────────────────────────
MAX_SECTOR_EXPOSURE = 0.25
HARD_KILL_SWITCH_VIX = float(os.getenv("HARD_KILL_SWITCH_VIX", "35.0"))
DRAWDOWN_RATE_KILL_WEEKLY = 5.0
CORRELATION_REDUCE_THRESHOLD = 0.75
CORRELATION_LIQUIDATE_THRESHOLD = 0.85

# ── Quality Thresholds ────────────────────────────────────────────────────────
MIN_MARKET_CAP_CR = 100
MIN_DATA_QUALITY = 40
MAX_FUNDAMENTAL_AGE_DAYS = int(os.getenv("MAX_FUNDAMENTAL_AGE_DAYS", "90"))
STALE_DATA_WARNING_DAYS = int(os.getenv("STALE_DATA_WARNING_DAYS", "60"))
FULL_SCAN_MIN_PASS_RATIO = 0.20
FULL_SCAN_DQ_FLOOR = 20
MAX_VECTORBT_SYMBOLS = 250
MIN_HISTORY_BARS = 120
MIN_FETCH_CORE_FIELDS = 2
MIN_FETCH_CORE_FIELDS_BY_SOURCE = {
    "pnsea": 1,
    "nsepython": 2,
    "yfinance": 2,
    "unknown": 2,
    "fallback_failed": 3,
}
SPARSE_FUNDAMENTAL_SOURCES = ["pnsea"]
SPARSE_SOURCE_MIN_CORE_FIELDS = 1
HARD_BLOCK_ZERO_VALUATION_FIELDS = True
DQ_ZERO_VALUATION_CAP = 20.0
FULL_SCAN_BASE_CONCURRENCY = 4
TARGET_SCAN_CONCURRENCY = 6
FULL_SCAN_RETRY_ENABLED = True
FULL_SCAN_RETRY_MIN_CONCURRENCY = 4
FULL_SCAN_RETRY_MAX_CONCURRENCY = 10
FULL_SCAN_RETRY_BACKOFF_SECONDS = 2.0
FULL_SCAN_RETRY_TRANSIENT_REASONS = [
    "fetch_failed",
    "fetch_exception",
    "no_price_history",
    "invalid_price",
]
IPO_SHORT_HISTORY_POLICY_ENABLE = True
IPO_SHORT_HISTORY_MIN_BARS = 90
IPO_SHORT_HISTORY_MIN_CORE_FIELDS = 4
IPO_SHORT_HISTORY_MAX_PRICE_AGE_DAYS = 7
IPO_SHORT_HISTORY_SOFT_FLAG = "short_history_ipo"
IPO_SHORT_HISTORY_DQ_PENALTY = 8.0

# ── Universe Hygiene ──────────────────────────────────────────────────────────
AUTO_FLAG_INVALID_SYMBOLS = True
UNIVERSE_FLAGS_PATH = "data/universe_flags.json"
AUTO_FLAG_FAILURE_THRESHOLD = 2
AUTO_FLAG_COOLDOWN_DAYS = 14
AUTO_FLAG_MIN_SUCCESS_RATIO = 0.40
AUTO_FLAG_MAX_NEW_INACTIVE_PER_RUN = 300
AUTO_FLAG_REASON_THRESHOLDS = {
    "no_price_history": 1,
    "no_fundamentals": 1,
    "invalid_price": 2,
    "short_history": 4,
    "missing_core_fields": 2,
    "incomplete_fundamentals": 3,
    "zero_valuation_fields": 1,
    "fetch_exception": 3,
    "fetch_failed": 2,
}
AUTO_FLAG_WHITELIST = [
    "RELIANCE.NS",
    "TCS.NS",
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "SBIN.NS",
]

# ── MiroFish Swarm Intelligence ───────────────────────────────────────────────
USE_MIROFISH: bool = os.getenv("USE_MIROFISH", "False").lower() == "true"
MIROFISH_URL: str = os.getenv("MIROFISH_API_URL", "http://localhost:5001/api")

# ── Scoring Weights ───────────────────────────────────────────────────────────
SCORING_WEIGHTS = {
    "balanced": {
        "w_sales": 0.15,
        "w_roe": 0.15,
        "w_cfo": 0.05,
        "w_val": 0.15,
        "w_eps": 0.10,
        "w_fscore": 0.10,
        "w_de": 0.10,
        "w_mom": 0.10,
        "w_sentiment": 0.10,  # Alternative Data Factor (v11.0)
    },
    "momentum": {
        "w_sales": 0.10,
        "w_roe": 0.00,
        "w_cfo": 0.00,
        "w_val": 0.00,
        "w_eps": 0.35,
        "w_fscore": 0.10,
        "w_de": 0.05,
        "w_mom": 0.25,
        "w_sentiment": 0.15,  # Aggressive news follow
    },
    "value": {
        "w_sales": 0.10,
        "w_roe": 0.15,
        "w_cfo": 0.10,
        "w_val": 0.30,
        "w_eps": 0.10,
        "w_fscore": 0.10,
        "w_de": 0.10,
        "w_mom": 0.00,
        "w_sentiment": 0.05,  # Conservative filtering
    },
    "quality": {
        "w_sales": 0.10,
        "w_roe": 0.20,
        "w_cfo": 0.15,
        "w_val": 0.10,
        "w_eps": 0.10,
        "w_fscore": 0.15,
        "w_de": 0.10,
        "w_mom": 0.00,
        "w_sentiment": 0.10,
    },
}

# ── Transaction Cost Model Components ──────────────────────────────────────────
TRANSACTION_COST = float(os.getenv("TRANSACTION_COST", "0.006"))
TC_STT_SELL = float(os.getenv("TC_STT_SELL", "0.001"))
TC_EXCHANGE = float(os.getenv("TC_EXCHANGE", "0.0000335"))
TC_SEBI_FEE = float(os.getenv("TC_SEBI_FEE", "0.000001"))
TC_STAMP_BUY = float(os.getenv("TC_STAMP_BUY", "0.00015"))
TC_IMPACT_ALPHA = float(os.getenv("TC_IMPACT_ALPHA", "0.001"))

TC_ADV_FRAC_LARGE = float(os.getenv("TC_ADV_FRAC_LARGE", "50.0"))
TC_ADV_FRAC_MID = float(os.getenv("TC_ADV_FRAC_MID", "10.0"))
TC_ADV_FRAC_SMALL = float(os.getenv("TC_ADV_FRAC_SMALL", "3.0"))

