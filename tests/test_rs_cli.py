import sqlite3
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sovereign_cli
from scripts.internal import cleanup_signals, ingest_rs_signals


def test_ingest_reads_csv_once_and_saves_dataframe(tmp_path, monkeypatch):
    csv_path = tmp_path / "tmp_rs_data.csv"
    csv_path.write_text(
        "\n".join(
            [
                "banner,,,,,,,",
                "generated,,,,,,,",
                "notes,,,,,,,",
                "#,Symbol,Company Name,Sector,Price,RS% (Window),DoD%,Signal",
                "1,ABC,ABC Ltd,Technology,123.45,0.45,1.2%,Strong Buy",
            ]
        ),
        encoding="utf-8",
    )

    read_calls = {"count": 0}
    original_read_csv = ingest_rs_signals.pd.read_csv
    saved = {}

    def counting_read_csv(*args, **kwargs):
        read_calls["count"] += 1
        return original_read_csv(*args, **kwargs)

    def fake_save_multibaggers(df):
        saved["df"] = df.copy()

    monkeypatch.setattr(ingest_rs_signals.pd, "read_csv", counting_read_csv)
    monkeypatch.setattr(ingest_rs_signals, "save_multibaggers", fake_save_multibaggers)

    count = ingest_rs_signals.ingest(csv_path=csv_path)

    assert count == 1
    assert read_calls["count"] == 1
    assert saved["df"]["Symbol"].tolist() == ["ABC.NS"]
    assert saved["df"]["Score"].tolist() == [88.0]
    assert saved["df"]["RS_Rating"].tolist() == [45.0]


def test_cleanup_symbols_deletes_requested_rows(tmp_path):
    db_path = tmp_path / "stocks.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE multibaggers (symbol TEXT)")
    conn.execute("CREATE TABLE fundamentals_pit (symbol TEXT)")
    conn.executemany(
        "INSERT INTO multibaggers (symbol) VALUES (?)",
        [("KEEP.NS",), ("DROP.NS",)],
    )
    conn.executemany(
        "INSERT INTO fundamentals_pit (symbol) VALUES (?)",
        [("DROP.NS",), ("OTHER.NS",)],
    )
    conn.commit()
    conn.close()

    deleted_rows = cleanup_signals.cleanup_symbols(["DROP.NS"], db_path=db_path)

    conn = sqlite3.connect(db_path)
    remaining_multibaggers = conn.execute(
        "SELECT symbol FROM multibaggers ORDER BY symbol"
    ).fetchall()
    remaining_pit = conn.execute(
        "SELECT symbol FROM fundamentals_pit ORDER BY symbol"
    ).fetchall()
    conn.close()

    assert deleted_rows == 2
    assert remaining_multibaggers == [("KEEP.NS",)]
    assert remaining_pit == [("OTHER.NS",)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("argv", "target"),
    [
        (
            ["sovereign_cli.py", "rs", "ingest", "--csv-path", "signals.csv"],
            "cmd_rs_ingest",
        ),
        (
            [
                "sovereign_cli.py",
                "rs",
                "enrich",
                "--db-path",
                "signals.db",
                "--delay-seconds",
                "0.5",
                "--market-regime",
                "BULL",
            ],
            "cmd_rs_enrich",
        ),
        (
            [
                "sovereign_cli.py",
                "rs",
                "cleanup",
                "--symbols",
                "AAA.NS",
                "BBB.NS",
                "--db-path",
                "signals.db",
            ],
            "cmd_rs_cleanup",
        ),
    ],
)
async def test_sovereign_cli_rs_dispatch(monkeypatch, argv, target):
    captured = {}

    async def fake_command(args):
        captured["args"] = args

    monkeypatch.setattr(sovereign_cli, target, fake_command)
    monkeypatch.setattr(sys, "argv", argv)

    await sovereign_cli.main()

    assert "args" in captured
    if target == "cmd_rs_ingest":
        assert captured["args"].csv_path == "signals.csv"
    elif target == "cmd_rs_enrich":
        assert captured["args"].db_path == "signals.db"
        assert captured["args"].delay_seconds == 0.5
        assert captured["args"].market_regime == "BULL"
    else:
        assert captured["args"].symbols == ["AAA.NS", "BBB.NS"]
        assert captured["args"].db_path == "signals.db"
