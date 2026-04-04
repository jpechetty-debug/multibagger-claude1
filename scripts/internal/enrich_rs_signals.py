from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from modules.fundamentals import calculate_piotroski_f_score
    from modules.scoring import calculate_institutional_score
except ImportError:
    def calculate_institutional_score(data, **kwargs):
        return {"total_score": 50}

    def calculate_piotroski_f_score(_ticker):
        return 5


DEFAULT_DB_PATH = PROJECT_ROOT / "stocks.db"


def _resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path

    cwd_candidate = Path.cwd() / path
    if cwd_candidate.exists():
        return cwd_candidate

    return PROJECT_ROOT / path


def enrich(
    db_path: str | Path = DEFAULT_DB_PATH,
    delay_seconds: float = 2.0,
    market_regime: str = "SIDEWAYS",
) -> int:
    resolved_db_path = _resolve_path(db_path)
    conn = sqlite3.connect(resolved_db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM multibaggers WHERE last_audited IS NULL")
    stocks = cursor.fetchall()

    if not stocks:
        print("No stocks found for enrichment.")
        conn.close()
        return 0

    print(
        f"Found {len(stocks)} stocks to enrich. "
        f"Starting throttled forensic scan ({delay_seconds:.1f}s delay)..."
    )

    enriched_count = 0
    for index, stock in enumerate(stocks, start=1):
        symbol = stock["symbol"]
        print(f"[{index}/{len(stocks)}] Deep scan: {symbol}...", end="\r")

        try:
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            ticker = yf.Ticker(symbol)
            info = ticker.info
            if not info or not info.get("currentPrice"):
                print(f"  Skipped {symbol} (no price data)")
                continue

            price = info.get("currentPrice") or 0
            name = info.get("shortName") or info.get("longName") or symbol
            sector = info.get("sector") or "Unknown"
            roe = (info.get("returnOnEquity") or 0) * 100
            pe = info.get("trailingPE") or info.get("forwardPE") or 0
            market_cap_cr = (info.get("marketCap") or 0) / 1e7
            debt_equity = (info.get("debtToEquity") or 0) / 100
            sales_growth = (info.get("revenueGrowth") or 0) * 100
            cfo = info.get("operatingCashflow") or 0
            pat = info.get("netIncomeToCommon") or 1
            cfo_pat = round(cfo / pat, 2) if pat > 0 else 0

            try:
                f_score = calculate_piotroski_f_score(ticker)
            except Exception:
                f_score = 5

            hist = ticker.history(period="1y")
            rs_rating = 0
            if not hist.empty and len(hist) > 126:
                price_6m_ago = hist["Close"].iloc[-126]
                rs_rating = (
                    round(((price - price_6m_ago) / price_6m_ago) * 100, 2)
                    if price_6m_ago > 0
                    else 0
                )

            high_52w = info.get("fiftyTwoWeekHigh", price)
            low_52w = info.get("fiftyTwoWeekLow", price)
            down_52w = (
                round(((high_52w - price) / high_52w) * 100, 2)
                if high_52w > 0
                else 0
            )

            score_data = {
                "ROE%": roe,
                "Sales_Growth_TTM%": sales_growth,
                "Debt_Equity": debt_equity,
                "F_Score": f_score,
                "PE_Ratio": pe,
                "Market_Cap_Cr": market_cap_cr,
                "Down_From_52W_High%": down_52w,
                "CFO_PAT_Ratio": cfo_pat,
                "RS_Rating": rs_rating,
            }

            try:
                score_res = calculate_institutional_score(
                    score_data,
                    market_regime=market_regime,
                )
                final_score = score_res.get("total_score", 50)
            except Exception:
                final_score = 50

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute(
                """
                UPDATE multibaggers
                SET name = ?,
                    price = ?,
                    sector = ?,
                    score = ?,
                    f_score = ?,
                    sales_growth = ?,
                    roe = ?,
                    debt_equity = ?,
                    market_cap_cr = ?,
                    cfo_pat_ratio = ?,
                    pe_ratio = ?,
                    down_from_52w = ?,
                    rs_rating = ?,
                    high_52w = ?,
                    low_52w = ?,
                    last_audited = ?,
                    updated_at = ?
                WHERE symbol = ?
                """,
                (
                    name,
                    price,
                    sector,
                    final_score,
                    f_score,
                    sales_growth,
                    roe,
                    debt_equity,
                    market_cap_cr,
                    cfo_pat,
                    pe,
                    down_52w,
                    rs_rating,
                    high_52w,
                    low_52w,
                    now_str,
                    now_str,
                    symbol,
                ),
            )

            enriched_count += 1
            if index % 5 == 0:
                conn.commit()
                print(f"\n[AUDIT] Checkpoint: commit for {index} symbols...")

        except Exception as exc:
            print(f"\n[ERROR] Failed to enrich {symbol}: {exc}")
            if "429" in str(exc):
                print("[SYSTEM] High rate limit detected. Sleeping 60s...")
                time.sleep(60)
            continue

    conn.commit()
    conn.close()
    print("\n" + "=" * 50)
    print(" FORENSIC ENRICHMENT COMPLETE")
    print(" Institutional signals synchronized.")
    print("=" * 50)
    return enriched_count


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Enrich RS signals already stored in stocks.db.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH), help="SQLite database path.")
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=2.0,
        help="Sleep interval between provider requests.",
    )
    parser.add_argument(
        "--market-regime",
        default="SIDEWAYS",
        help="Market regime passed into institutional scoring.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    enrich(
        db_path=args.db_path,
        delay_seconds=args.delay_seconds,
        market_regime=args.market_regime,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
