#!/usr/bin/env python
"""Seed dq_sector_limits with sector-specific metric ranges for 12 Indian market sectors.

Idempotent: uses INSERT OR REPLACE so safe to re-run.
Run:  python scripts/seed_dq_limits.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from db.repository import _ensure_dq_sector_limits_table, get_connection  # noqa: E402

# ── Sector-Specific Limit Definitions ─────────────────────────────────────────
# Only metrics whose reasonable range differs materially from METRIC_LIMITS
# defaults are specified here. Unspecified metrics fall back to the global
# flat limits in dq_gates.METRIC_LIMITS.
#
# Format: (sector, metric, min_val, max_val, auto_scale_threshold)

SECTOR_LIMITS: list[tuple[str, str, float, float, float | None]] = [
    # ── Banking ────────────────────────────────────────────────────────────────
    # Banks: low PE (5-25), high D/E is structural (leverage-based model),
    # ROE typically 10-20%, CFO/PAT ratio less meaningful for banks.
    ("Banking", "pe_ratio", -20, 40, None),
    ("Banking", "debt_equity", 0, 20, None),         # leverage is the business
    ("Banking", "roe", -50, 100, None),
    ("Banking", "cfo_pat_ratio", -20, 30, None),

    # ── IT ─────────────────────────────────────────────────────────────────────
    # IT: higher PE normal (30-80), near-zero debt, high ROE, strong CFO/PAT.
    ("IT", "pe_ratio", -20, 120, None),
    ("IT", "debt_equity", 0, 5, None),
    ("IT", "roe", -50, 300, None),
    ("IT", "cfo_pat_ratio", -5, 25, None),

    # ── Pharma ─────────────────────────────────────────────────────────────────
    # Pharma: moderate-high PE (15-60), low-moderate debt, R&D variability.
    ("Pharma", "pe_ratio", -20, 80, None),
    ("Pharma", "debt_equity", 0, 10, None),
    ("Pharma", "roe", -100, 200, None),
    ("Pharma", "eps_growth", -200, 500, None),

    # ── NBFC ───────────────────────────────────────────────────────────────────
    # NBFCs: similar to banks but higher risk tolerance.
    ("NBFC", "pe_ratio", -20, 50, None),
    ("NBFC", "debt_equity", 0, 15, None),
    ("NBFC", "roe", -100, 150, None),
    ("NBFC", "cfo_pat_ratio", -20, 30, None),

    # ── Energy ─────────────────────────────────────────────────────────────────
    # Energy: cyclical PE, moderate debt, commodity-driven.
    ("Energy", "pe_ratio", -50, 60, None),
    ("Energy", "debt_equity", 0, 10, None),
    ("Energy", "roe", -100, 150, None),
    ("Energy", "sales_cagr_5y", -50, 200, None),

    # ── Metals ─────────────────────────────────────────────────────────────────
    # Metals: highly cyclical, PE can swing wildly, moderate debt.
    ("Metals", "pe_ratio", -100, 100, None),
    ("Metals", "debt_equity", 0, 10, None),
    ("Metals", "roe", -200, 200, None),
    ("Metals", "eps_growth", -500, 1000, None),

    # ── Aviation ───────────────────────────────────────────────────────────────
    # Aviation: often negative earnings, high debt, volatile.
    ("Aviation", "pe_ratio", -100, 200, None),
    ("Aviation", "debt_equity", 0, 30, None),
    ("Aviation", "roe", -500, 200, None),
    ("Aviation", "cfo_pat_ratio", -20, 30, None),

    # ── Realty ─────────────────────────────────────────────────────────────────
    # Realty: project-based revenue, high debt, cyclical PE.
    ("Realty", "pe_ratio", -50, 100, None),
    ("Realty", "debt_equity", 0, 15, None),
    ("Realty", "roe", -100, 200, None),
    ("Realty", "cfo_pat_ratio", -15, 20, None),

    # ── FMCG ──────────────────────────────────────────────────────────────────
    # FMCG: premium PE, low debt, stable ROE.
    ("FMCG", "pe_ratio", -10, 100, None),
    ("FMCG", "debt_equity", 0, 5, None),
    ("FMCG", "roe", -20, 200, None),
    ("FMCG", "dividend_yield", 0, 10, 10),

    # ── Chemicals ──────────────────────────────────────────────────────────────
    # Chemicals: moderate PE, moderate debt, cyclical margins.
    ("Chemicals", "pe_ratio", -20, 80, None),
    ("Chemicals", "debt_equity", 0, 8, None),
    ("Chemicals", "roe", -100, 200, None),
    ("Chemicals", "eps_growth", -300, 500, None),

    # ── Infra ──────────────────────────────────────────────────────────────────
    # Infra: government-driven, high debt, long gestation PE.
    ("Infra", "pe_ratio", -50, 80, None),
    ("Infra", "debt_equity", 0, 15, None),
    ("Infra", "roe", -100, 150, None),
    ("Infra", "cfo_pat_ratio", -15, 20, None),

    # ── Auto ───────────────────────────────────────────────────────────────────
    # Auto: cyclical PE, moderate debt, OEM vs ancillary differences.
    ("Auto", "pe_ratio", -30, 80, None),
    ("Auto", "debt_equity", 0, 10, None),
    ("Auto", "roe", -100, 200, None),
    ("Auto", "sales_cagr_5y", -50, 300, None),
]


def seed(*, verbose: bool = True) -> int:
    """Insert or replace sector limit rows. Returns count of rows written."""
    conn = get_connection()
    try:
        _ensure_dq_sector_limits_table(conn)
        conn.executemany(
            """
            INSERT OR REPLACE INTO dq_sector_limits
            (sector, metric, min_val, max_val, auto_scale_threshold)
            VALUES (?, ?, ?, ?, ?)
            """,
            SECTOR_LIMITS,
        )
        conn.commit()
        count = len(SECTOR_LIMITS)
        if verbose:
            sectors = sorted({row[0] for row in SECTOR_LIMITS})
            print(f"Seeded {count} sector-limit rows across {len(sectors)} sectors:")
            for s in sectors:
                metrics = [row[1] for row in SECTOR_LIMITS if row[0] == s]
                print(f"  {s}: {', '.join(metrics)}")
        return count
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
