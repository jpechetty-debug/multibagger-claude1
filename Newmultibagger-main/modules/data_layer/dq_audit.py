"""
Strict data-quality audit for the `multibaggers` picks table.

Catches the failure modes that silently corrupted picks before:
  * zero_fill    - a column with too many exact zeros (missing stored as 0)
  * constant     - a column with one value for every row (pledge was 0% for all 516)
  * dead         - a column that is NULL for every row (field dropped on save)
  * low_coverage - a core scoring input missing for too many rows
  * saturated    - too many values pinned at a DQ clamp bound (RS stuck at 0 or 10)
  * inverted     - a derived signal that disagrees with its own input (RS vs 6M return)
  * placeholder  - a label standing in for missing data (sector "Unknown")
  * duplicates   - the same symbol saved twice
  * stale        - the newest saved row is older than MAX_AGE_DAYS

Every check fails the audit. A known issue can be waived only in WAIVERS, with a
reason and an expiry date; an expired waiver fails again, so nothing stays hidden.

Usage:
    python -m modules.data_layer.dq_audit            # audit runtime/stocks.db, exit 1 on failure
    python -m modules.data_layer.dq_audit --db path
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "runtime" / "stocks.db"

# Columns where an exact 0 is a real, common value.
ZERO_OK = {"conviction_boost", "institutional_interest", "sector_leader", "dividend_yield",
           "dividend_payout", "analyst_upside", "vol_breakout", "earnings_accel"}
MAX_ZERO_SHARE = 0.10

# Core scoring inputs: at most this share of rows may be NULL.
CORE_COVERAGE = {"price": 0.0, "score": 0.0, "market_cap_cr": 0.0, "roe": 0.10,
                 "sales_cagr_5y": 0.15, "debt_equity": 0.20, "cfo_pat_ratio": 0.25,
                 "pe_ratio": 0.20, "rs_rating": 0.05, "ret_6m": 0.05}

# (column, low, high): DQ-gate clamp bounds a healthy column should rarely sit on.
CLAMP_BOUNDS = [("rs_rating", 0.0, 10.0), ("value_gap", -100.0, 500.0),
                ("sales_cagr_5y", -100.0, 500.0), ("revenue_cagr_3y", -100.0, 500.0)]
MAX_SATURATED_SHARE = 0.05

# (signal, input, min Spearman): the signal must rise with its input.
MONOTONIC = [("rs_rating", "ret_6m", 0.9)]

# (column, placeholder, max share): placeholder labels standing in for missing data.
PLACEHOLDERS = [
    ("sector", "Unknown", 0.02),
    ("data_source", "fallback_failed", 0.02),  # every provider failed for this stock
    ("data_source", "unknown", 0.02),
]

MIN_ROWS = 50
MAX_AGE_DAYS = 7  # picks must come from a scan at most a week old

# Known issues being worked on. Key: (check, column). Value: (reason, expiry ISO date).
WAIVERS: dict[tuple[str, str], tuple[str, str]] = {
    ("constant", "earnings_accel"): ("fixed in 9d94cda; stored rows refresh on next scan", "2026-10-20"),
    ("zero_fill", "backtest_cagr"): ("fixed: unbacktested picks now None; stored zeros clear on next scan", "2026-10-20"),
    ("zero_fill", "backtest_win_rate"): ("fixed: unbacktested picks now None; stored zeros clear on next scan", "2026-10-20"),
    ("zero_fill", "backtest_max_dd"): ("fixed: unbacktested picks now None; stored zeros clear on next scan", "2026-10-20"),
    ("zero_fill", "backtest_sharpe"): ("fixed: unbacktested picks now None; stored zeros clear on next scan", "2026-10-20"),
    ("dead", "data_source"): ("provenance column added 2026-10-07; filled by the next scan", "2026-10-13"),
    ("dead", "data_freshness"): ("provenance column added 2026-10-07; filled by the next scan", "2026-10-13"),
    ("placeholder", "sector"): ("fixed in code; stored rows refresh on next scan", "2026-10-13"),
    ("dead", "pledge_pct"): ("no free source: Screener.in pages carry no pledge row", "2026-12-31"),
    **{("dead", c): ("computed by the scan but dropped on save; fix next", "2026-10-13") for c in (
        "roce", "revenue_cagr_5y", "pat_cagr_5y", "eps_cagr_5y", "median_pat_growth", "piotroski_score",
        "roa_pct", "net_margin_pct", "asset_turnover", "financial_leverage", "ocf_yield",
        "earnings_velocity_qoq", "earnings_velocity_yoy", "down_from_52w_high", "shap_top_drivers")},
    **{("dead", c): ("unused column; drop or populate", "2026-10-13") for c in ("target_2", "last_audited")},
}


@dataclass
class Finding:
    check: str
    column: str
    detail: str
    waived_until: str | None = None


def _spearman(xs: list[float], ys: list[float]) -> float:
    def ranks(v: list[float]) -> list[float]:
        order = sorted(range(len(v)), key=v.__getitem__)
        r = [0.0] * len(v)
        for rank, i in enumerate(order):
            r[i] = float(rank)
        return r

    rx, ry = ranks(xs), ranks(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    vx = sum((a - mx) ** 2 for a in rx) ** 0.5
    vy = sum((b - my) ** 2 for b in ry) ** 0.5
    return cov / (vx * vy) if vx and vy else 0.0


def audit(conn: sqlite3.Connection, table: str = "multibaggers", today: date | None = None) -> list[Finding]:
    """Return every finding; waived ones carry their expiry in ``waived_until``."""
    today = today or date.today()
    found: list[Finding] = []
    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if n < MIN_ROWS:
        return [Finding("row_count", "*", f"only {n} rows (< {MIN_ROWS})")]

    newest = conn.execute(f"SELECT MAX(updated_at) FROM {table}").fetchone()[0] if any(
        r[1] == "updated_at" for r in conn.execute(f"PRAGMA table_info({table})")) else None
    if newest:
        age = (today - date.fromisoformat(str(newest)[:10])).days
        if age > MAX_AGE_DAYS:
            found.append(Finding("stale", "updated_at", f"newest row is {age} days old (limit {MAX_AGE_DAYS})"))

    dupes = conn.execute(f"SELECT COUNT(*) - COUNT(DISTINCT symbol) FROM {table}").fetchone()[0]
    if dupes:
        found.append(Finding("duplicates", "symbol", f"{dupes} duplicate symbols"))

    schema = [(col, ctype) for _, col, ctype, *_ in conn.execute(f"PRAGMA table_info({table})")]
    present = {col for col, _ in schema}
    for col, ctype in schema:
        nulls, zeros, distinct = conn.execute(
            f'SELECT SUM("{col}" IS NULL), SUM("{col}" = 0), COUNT(DISTINCT "{col}") FROM {table}'
        ).fetchone()
        if nulls == n:
            found.append(Finding("dead", col, "NULL for every row"))
            continue
        if distinct == 1 and nulls == 0 and col not in ("as_of_date", "updated_at"):
            value = conn.execute(f'SELECT "{col}" FROM {table} LIMIT 1').fetchone()[0]
            found.append(Finding("constant", col, f"every row = {value!r}"))
            continue
        numeric = ctype.upper() in ("REAL", "INTEGER", "FLOAT", "NUMERIC")
        if numeric and col not in ZERO_OK and zeros and zeros / n > MAX_ZERO_SHARE:
            found.append(Finding("zero_fill", col, f"{zeros}/{n} rows are exactly 0"))
        if col in CORE_COVERAGE and nulls / n > CORE_COVERAGE[col]:
            found.append(Finding("low_coverage", col, f"{nulls}/{n} NULL (limit {CORE_COVERAGE[col]:.0%})"))

    for col, placeholder, limit in (ph for ph in PLACEHOLDERS if ph[0] in present):
        hits = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} = ? OR {col} = ''", (placeholder,)).fetchone()[0]
        if hits / n > limit:
            found.append(Finding("placeholder", col, f"{hits}/{n} rows are {placeholder!r} (limit {limit:.0%})"))

    for col, lo, hi in (b for b in CLAMP_BOUNDS if b[0] in present):
        pinned = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {col} <= ? OR {col} >= ?", (lo, hi)).fetchone()[0]
        if pinned / n > MAX_SATURATED_SHARE:
            found.append(Finding("saturated", col, f"{pinned}/{n} rows at clamp bound {lo} or {hi}"))

    for signal, source, min_rho in (m for m in MONOTONIC if {m[0], m[1]} <= present):
        pairs = conn.execute(
            f"SELECT {signal}, {source} FROM {table} WHERE {signal} IS NOT NULL AND {source} IS NOT NULL"
        ).fetchall()
        if len(pairs) >= MIN_ROWS:
            rho = _spearman([p[0] for p in pairs], [p[1] for p in pairs])
            if rho < min_rho:
                found.append(Finding("inverted", signal, f"Spearman vs {source} = {rho:.2f} (< {min_rho})"))

    for f in found:
        waiver = WAIVERS.get((f.check, f.column))
        if waiver and date.fromisoformat(waiver[1]) >= today:
            f.waived_until = waiver[1]
            f.detail += f"  [waived: {waiver[0]}]"
    return found


def report(findings: list[Finding]) -> bool:
    """Print the findings; return True when nothing unwaived remains."""
    failures = [f for f in findings if not f.waived_until]
    for f in sorted(findings, key=lambda f: (bool(f.waived_until), f.check, f.column)):
        tag = f"WAIVED to {f.waived_until}" if f.waived_until else "FAIL"
        print(f"  [{tag}] {f.check:12} {f.column:24} {f.detail}")
    print(f"DQ audit: {len(failures)} failures, {len(findings) - len(failures)} waived")
    return not failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args(argv)
    conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    try:
        return 0 if report(audit(conn)) else 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
