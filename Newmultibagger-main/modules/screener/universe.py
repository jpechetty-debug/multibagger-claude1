"""
Universe management: load/save/refresh blocked symbols and flags.

Extracted from scripts/internal/screener.py.
"""

import json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo


_FLAGS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "universe_flags.json"


def load_universe_flags(path=None):
    """Load universe flags from JSON file."""
    fp = Path(path) if path else _FLAGS_PATH
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_universe_flags(flags, path=None):
    """Save universe flags to JSON file."""
    fp = Path(path) if path else _FLAGS_PATH
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(flags, indent=2, default=str), encoding="utf-8")


def refresh_and_get_blocked_symbols(flags, *, stale_days=30):
    """Return set of symbols that should be skipped (blocked/delisted)."""
    blocked = set()
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    for symbol, meta in flags.items():
        status = meta.get("status", "")
        if status in ("blocked", "delisted"):
            blocked.add(symbol)
        elif status == "stale":
            last_ok = meta.get("last_ok")
            if last_ok:
                try:
                    dt = datetime.fromisoformat(last_ok)
                    if (now - dt).days > stale_days:
                        blocked.add(symbol)
                except Exception:
                    pass
    return blocked


def update_universe_flags(flags, symbol, *, status="ok", reason="", score=None):
    """Update flags for a single symbol."""
    now = datetime.now(ZoneInfo("Asia/Kolkata")).isoformat()
    entry = flags.get(symbol, {})
    entry["status"] = status
    entry["updated_at"] = now
    if reason:
        entry["reason"] = reason
    if score is not None:
        entry["last_score"] = score
    if status == "ok":
        entry["last_ok"] = now
    flags[symbol] = entry
    return flags
