import sqlite3
from datetime import date

import pytest

from modules.data_layer import dq_audit

N = 100


def _db(path=":memory:", **overrides):
    """A clean picks table; each override is (column, value_fn(i))."""
    cols = {
        "symbol": lambda i: f"S{i}.NS",
        "price": lambda i: 100.0 + i,
        "score": lambda i: 40.0 + i * 0.3,
        "market_cap_cr": lambda i: 500.0 + i,
        "roe": lambda i: 5.0 + i * 0.2,
        "debt_equity": lambda i: 0.1 + i * 0.01,
        "ret_6m": lambda i: -0.5 + i * 0.02,
        "rs_rating": lambda i: round((1 + (-0.5 + i * 0.02)) / 1.01, 3),
    }
    cols.update(overrides)
    conn = sqlite3.connect(path)
    types = {c: ("TEXT" if c == "symbol" else "REAL") for c in cols}
    conn.execute(f"CREATE TABLE multibaggers ({', '.join(f'{c} {t}' for c, t in types.items())})")
    rows = [tuple(fn(i) for fn in cols.values()) for i in range(N)]
    conn.executemany(f"INSERT INTO multibaggers VALUES ({', '.join('?' * len(cols))})", rows)
    return conn


def _checks(conn, today=date(2026, 10, 6)):
    return {(f.check, f.column) for f in dq_audit.audit(conn, today=today) if not f.waived_until}


def test_clean_table_passes():
    assert _checks(_db()) == set()


def test_missing_stored_as_zero_fails():
    # The D/E bug: 93/516 picks stored 0 for "unknown", scored as debt-free.
    conn = _db(debt_equity=lambda i: 0.0 if i < 20 else 0.5)
    assert ("zero_fill", "debt_equity") in _checks(conn)


def test_constant_column_fails():
    # The pledge bug: every pick stored 0%.
    conn = _db(pledge_pct=lambda i: 0.0)
    assert ("constant", "pledge_pct") in _checks(conn)


def test_dead_column_fails():
    assert ("dead", "new_metric") in _checks(_db(new_metric=lambda i: None))


def test_inverted_and_saturated_rs_fails():
    # The RS bug: dividing by a tiny Nifty return pinned RS at 0 or 10, top gainers at 0.
    conn = _db(rs_rating=lambda i: 0.0 if i > N / 2 else 10.0)
    found = _checks(conn)
    assert ("inverted", "rs_rating") in found
    assert ("saturated", "rs_rating") in found


def test_low_coverage_of_core_input_fails():
    conn = _db(roe=lambda i: None if i < 30 else 12.0)
    assert ("low_coverage", "roe") in _checks(conn)


def test_duplicate_symbols_fail():
    assert ("duplicates", "symbol") in _checks(_db(symbol=lambda i: f"S{i % 90}.NS"))


def test_waiver_hides_until_expiry_then_fails(monkeypatch):
    monkeypatch.setattr(dq_audit, "WAIVERS", {("dead", "roce"): ("being fixed", "2026-10-10")})
    conn = _db(roce=lambda i: None)
    assert ("dead", "roce") not in _checks(conn, today=date(2026, 10, 9))
    assert ("dead", "roce") in _checks(conn, today=date(2026, 10, 11))


def test_cli_exit_code(tmp_path):
    path = tmp_path / "picks.db"
    conn = _db(str(path), debt_equity=lambda i: 0.0)
    conn.commit()
    conn.close()
    assert dq_audit.main(["--db", str(path)]) == 1


@pytest.mark.parametrize("rows", [0, 10])
def test_too_few_rows_fails(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE multibaggers (symbol TEXT, score REAL)")
    conn.executemany("INSERT INTO multibaggers VALUES (?, ?)", [(f"S{i}", 1.0) for i in range(rows)])
    assert ("row_count", "*") in _checks(conn)


def test_unknown_sector_placeholder_fails():
    conn = _db(sector=lambda i: "Unknown" if i < 10 else "Industrials")
    assert ("placeholder", "sector") in _checks(conn, today=date(2026, 12, 1))
