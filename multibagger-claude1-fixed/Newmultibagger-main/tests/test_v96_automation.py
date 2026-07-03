import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add root to sys.path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

import sovereign_cli
from sovereign_cli import _run_paper_trade_scan, cmd_db_dups, cmd_paper_trade

# ══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_signals_log(tmp_path, monkeypatch):
    """Create a temporary signal log file and monkeypatch SIGNALS_LOG."""
    log_file = tmp_path / "test_signals.json"
    with open(log_file, "w") as f:
        json.dump([], f)
    monkeypatch.setattr(sovereign_cli, "SIGNALS_LOG", str(log_file))
    return log_file


# ══════════════════════════════════════════════════════════════════════════════
# TEST CASES
# ══════════════════════════════════════════════════════════════════════════════


def test_score_hard_floor():
    """Verify that _run_paper_trade_scan returns raw scores correctly."""
    universe = ["STK1.NS", "STK2.NS", "STK3.NS"]
    regime = "BULL"

    with (
        patch("yfinance.Ticker") as mock_ticker,
        patch("modules.scoring.calculate_institutional_score") as mock_score,
        patch("modules.fundamentals.calculate_piotroski_f_score") as mock_f_score,
    ):
        mock_ticker.return_value.info = {"currentPrice": 100, "sector": "Tech"}
        mock_f_score.return_value = 7
        mock_score.side_effect = [{"total_score": 8.0}, {"total_score": 5.0}, {"total_score": 0.0}]

        results = _run_paper_trade_scan(universe, regime)
        self_scores = [r["total_score"] for r in results]
        assert 8.0 in self_scores
        assert 5.0 in self_scores
        assert 0.0 in self_scores


@pytest.mark.asyncio
async def test_cmd_paper_trade_filters_score(mock_signals_log, monkeypatch):
    """Verify cmd_paper_trade correctly applies the > 5 filter at the CLI layer."""
    args = MagicMock()
    args.universe = 3
    args.force = True

    # Use direct monkeypatching for the scan logic - most robust
    monkeypatch.setattr(
        sovereign_cli,
        "_run_paper_trade_scan",
        lambda *a: [
            {"Symbol": "GOOD1", "total_score": 8.5, "Price": 100},
            {"Symbol": "BAD1", "total_score": 5.0, "Price": 90},
            {"Symbol": "ZERO1", "total_score": 0.0, "Price": 80},
        ],
    )

    with patch("sovereign_cli.MarketDataProvider") as mock_m:
        mock_m.return_value.get_market_regime.return_value = {"regime": "BULL"}
        await cmd_paper_trade(args)

    with open(mock_signals_log) as f:
        history = json.load(f)
        picks = history[0]["picks"]
        assert "GOOD1" in picks
        assert "BAD1" not in picks


@pytest.mark.asyncio
async def test_concentration_cap_logic(mock_signals_log, monkeypatch):
    """Verify that a stock held for 2 quarters is blocked in the 3rd."""
    args = MagicMock()
    args.universe = 5
    args.force = True

    history = [{"picks": ["HOLD.NS"]}, {"picks": ["HOLD.NS"]}]
    with open(mock_signals_log, "w") as f:
        json.dump(history, f)

    monkeypatch.setattr(
        sovereign_cli,
        "_run_paper_trade_scan",
        lambda *a: [
            {"Symbol": "HOLD.NS", "total_score": 9.9, "Price": 100},
            {"Symbol": "NEW1.NS", "total_score": 8.0, "Price": 50},
        ],
    )

    with patch("sovereign_cli.MarketDataProvider") as mock_m:
        mock_m.return_value.get_market_regime.return_value = {"regime": "BULL"}
        await cmd_paper_trade(args)

    with open(mock_signals_log) as f:
        final_history = json.load(f)
        latest_picks = final_history[-1]["picks"]
        assert "HOLD.NS" not in latest_picks
        assert "NEW1.NS" in latest_picks


@pytest.mark.asyncio
async def test_db_dups_forensic():
    """Verify cmd_db_dups correctly identifies duplicate records."""
    test_db = "temp_tests.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    conn = sqlite3.connect(test_db)
    conn.execute("CREATE TABLE multibaggers (symbol TEXT, count INTEGER)")
    conn.execute("INSERT INTO multibaggers VALUES ('AB.NS', 1)")
    conn.execute("INSERT INTO multibaggers VALUES ('AB.NS', 1)")
    conn.commit()
    conn.close()

    args = MagicMock()
    args.group = "sys"
    args.command = "dups"
    # Patch specifically the sqlite3.connect within the module
    with (
        patch("sovereign_cli.sqlite3.connect") as mock_connect,
        patch("builtins.print") as mock_print,
    ):
        mock_connect.return_value = sqlite3.connect(test_db)
        await cmd_db_dups(args)

        printed = [str(c.args[0]) for c in mock_print.call_args_list]
        assert any("AB.NS" in p for p in printed)
        mock_connect.return_value.close()

    if os.path.exists(test_db):
        os.remove(test_db)


@pytest.mark.asyncio
async def test_cmd_regime_prints_regime_and_acceleration():
    args = MagicMock()

    with (
        patch("sovereign_cli.MarketDataProvider") as mock_provider,
        patch("builtins.print") as mock_print,
    ):
        mock_provider.return_value.get_market_regime.return_value = {
            "regime": "SIDEWAYS",
            "details": {"momentum_accel": 1.25},
        }
        await sovereign_cli.cmd_regime(args)

    printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
    assert "Current Regime: SIDEWAYS" in printed
    assert "Acceleration: 1.25" in printed


@pytest.mark.asyncio
async def test_cmd_paper_trade_skips_non_rebalance_without_force(mock_signals_log, monkeypatch):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 3, 9, 0, 0)

    monkeypatch.setattr(sovereign_cli, "datetime", FakeDateTime)

    args = MagicMock()
    args.universe = 5
    args.force = False

    with (
        patch("sovereign_cli.MarketDataProvider") as mock_provider,
        patch("builtins.print") as mock_print,
    ):
        await sovereign_cli.cmd_paper_trade(args)

    with open(mock_signals_log) as handle:
        history = json.load(handle)

    printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
    assert history == []
    assert "Today is not a rebalance date" in printed
    mock_provider.assert_not_called()
