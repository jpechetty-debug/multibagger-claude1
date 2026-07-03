from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sovereign_cli


def _sample_result():
    return {
        "status": "OK",
        "strategy": "xgboost_walk_forward",
        "rebalance_frequency": "M",
        "benchmark_symbol": "^CNX500",
        "benchmark_status": "OK",
        "folds": 1,
        "top_quantile": 0.8,
        "max_positions": 5,
        "cagr": 14.2,
        "gross_cagr": 15.0,
        "transaction_cost_drag": 0.8,
        "benchmark_cagr": 9.1,
        "alpha_cagr": 5.1,
        "alpha_monthly": 0.4,
        "beta": 0.9,
        "tracking_error": 6.2,
        "information_ratio": 0.77,
        "max_drawdown": -8.5,
        "sharpe_ratio": 1.4,
        "win_rate": 60.0,
        "turnover": 1.2,
        "avg_turnover": 0.4,
        "fold_details": [
            {
                "test_period": "2025-04",
                "train_start_period": "2024-01",
                "train_end_period": "2025-03",
                "candidate_count": 20,
                "selected_count": 4,
                "selected_symbols": ["AAA.NS", "BBB.NS"],
                "gross_return": 0.03,
                "net_return": 0.024,
                "turnover": 1.0,
            }
        ],
    }


def test_write_walk_forward_report_creates_readable_markdown(tmp_path):
    report_path = tmp_path / "reports" / "walk_forward.md"

    written = sovereign_cli._write_walk_forward_report(_sample_result(), report_path)

    assert written == str(report_path.resolve())
    text = report_path.read_text(encoding="utf-8")
    assert "# Sovereign Walk-Forward Portfolio Backtest" in text
    assert "| Alpha CAGR | +5.10% |" in text
    assert "AAA.NS, BBB.NS" in text


@pytest.mark.asyncio
async def test_cmd_backtest_walk_forward_runs_engine_and_writes_report(tmp_path, monkeypatch):
    captured = {}

    class FakeEngine:
        def run_walk_forward_strategy_backtest(self, symbols, **kwargs):
            captured["symbols"] = symbols
            captured["kwargs"] = kwargs
            return _sample_result()

    def fake_engine(period, transaction_cost, benchmark_symbol):
        captured["engine"] = {
            "period": period,
            "transaction_cost": transaction_cost,
            "benchmark_symbol": benchmark_symbol,
        }
        return FakeEngine()

    monkeypatch.setattr(sovereign_cli, "_load_walk_forward_symbols", lambda args: ["AAA.NS"])
    monkeypatch.setattr(sovereign_cli, "_build_vectorbt_engine", fake_engine)

    args = SimpleNamespace(
        period="3y",
        transaction_cost=0.006,
        benchmark="^CNX500",
        min_train_periods=4,
        rebalance="monthly",
        top_quantile=0.75,
        max_positions=3,
        report_path=str(tmp_path / "wf_report.md"),
    )

    result = await sovereign_cli.cmd_backtest_walk_forward(args)

    assert result["status"] == "OK"
    assert captured["symbols"] == ["AAA.NS"]
    assert captured["engine"]["period"] == "3y"
    assert captured["kwargs"]["min_train_periods"] == 4
    assert captured["kwargs"]["rebalance_frequency"] == "monthly"
    assert Path(args.report_path).exists()


@pytest.mark.asyncio
async def test_sovereign_cli_backtest_walk_forward_dispatch(monkeypatch, tmp_path):
    captured = {}

    async def fake_command(args):
        captured["args"] = args

    monkeypatch.setattr(sovereign_cli, "cmd_backtest_walk_forward", fake_command)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sovereign_cli.py",
            "backtest",
            "walk-forward",
            "--symbols",
            "AAA.NS,BBB.NS",
            "--rebalance",
            "monthly",
            "--min-train-periods",
            "6",
            "--report-path",
            str(tmp_path / "wf.md"),
        ],
    )

    await sovereign_cli.main()

    assert captured["args"].symbols == "AAA.NS,BBB.NS"
    assert captured["args"].rebalance == "monthly"
    assert captured["args"].min_train_periods == 6
