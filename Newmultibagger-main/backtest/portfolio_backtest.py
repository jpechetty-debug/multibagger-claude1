"""
Portfolio-Level Backtest
=========================
Time-machine backtest: for each quarter, run the screener with PIT data,
take top-N picks, and measure actual forward returns.

This is the critical validation piece — it answers: "If I had run this
screener 1/2/3 years ago, would the top-20 picks have actually been
multibaggers?"
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from core.observability.logger import get_logger

_log = get_logger("backtest.portfolio_backtest")


@dataclass
class QuarterResult:
    quarter: str
    n_picks: int
    avg_return: float | None
    median_return: float | None
    hit_rate: float | None  # % of picks with return > 0
    multibagger_rate: float | None  # % of picks with return > 30%
    max_return: float | None
    min_return: float | None
    benchmark_return: float | None  # Nifty 50 return over same period

    def to_dict(self) -> dict[str, Any]:
        return {
            "quarter": self.quarter,
            "n_picks": self.n_picks,
            "avg_return": self.avg_return,
            "median_return": self.median_return,
            "hit_rate": self.hit_rate,
            "multibagger_rate": self.multibagger_rate,
            "max_return": self.max_return,
            "min_return": self.min_return,
            "benchmark_return": self.benchmark_return,
        }


@dataclass
class BacktestReport:
    status: str  # "OK" | "SKIPPED"
    reason: str = ""
    total_quarters: int = 0
    avg_hit_rate: float | None = None
    avg_multibagger_rate: float | None = None
    avg_return: float | None = None
    avg_excess_return: float | None = None  # vs benchmark
    quarters: list[QuarterResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "total_quarters": self.total_quarters,
            "avg_hit_rate": self.avg_hit_rate,
            "avg_multibagger_rate": self.avg_multibagger_rate,
            "avg_return": self.avg_return,
            "avg_excess_return": self.avg_excess_return,
            "quarters": [q.to_dict() for q in self.quarters],
        }


def _load_pit_data() -> pd.DataFrame:
    """Load all PIT data with features for backtesting."""
    try:
        from modules.data_layer.db_utils import get_db_connection

        with get_db_connection("stocks.db") as conn:
            df = pd.read_sql(
                """
                SELECT symbol, as_of_date,
                       price AS pit_price,
                       score, sales_cagr_5y, avg_roe_5y, pe_ratio,
                       debt_equity, cfo_pat_ratio, market_cap_cr,
                       ret_1m, ret_3m, ret_6m,
                       vol_breakout, dist_from_52w_high, roce,
                       sector
                FROM fundamentals_pit
                WHERE score IS NOT NULL
                ORDER BY as_of_date
                """,
                conn,
            )
        df["as_of_date"] = pd.to_datetime(df["as_of_date"], errors="coerce")
        return df.dropna(subset=["as_of_date"])
    except Exception as exc:
        _log.error("Failed to load PIT data", error=str(exc))
        return pd.DataFrame()


def _get_forward_price(symbol: str, as_of_date: pd.Timestamp, months: int = 6) -> float | None:
    """Get the price of a symbol approximately `months` after `as_of_date`."""
    try:
        from modules.data_layer.db_utils import get_db_connection

        target_date = as_of_date + pd.DateOffset(months=months)
        clean_sym = symbol.replace(".NS", "").replace(".BO", "")

        with get_db_connection("pit_store.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT value, as_of_date FROM pit_data
                WHERE symbol = ? AND metric_name = 'price'
                AND as_of_date >= ? AND value IS NOT NULL
                ORDER BY as_of_date ASC LIMIT 1
                """,
                (clean_sym, target_date.strftime("%Y-%m-%d")),
            )
            row = cursor.fetchone()
            if row and row[0] is not None:
                found_date = pd.to_datetime(row[1])
                if (found_date - target_date).days <= 45:
                    return float(row[0])
    except Exception:
        pass
    return None


def _get_benchmark_return(as_of_date: pd.Timestamp, months: int = 6) -> float | None:
    """Get Nifty 50 return over the forward period."""
    try:
        from modules.data_layer.db_utils import get_db_connection

        target_date = as_of_date + pd.DateOffset(months=months)

        with get_db_connection("pit_store.db") as conn:
            cursor = conn.cursor()
            # Get price at as_of_date
            cursor.execute(
                """
                SELECT value FROM pit_data
                WHERE symbol = 'NIFTY50' AND metric_name = 'price'
                AND as_of_date <= ? AND value IS NOT NULL
                ORDER BY as_of_date DESC LIMIT 1
                """,
                (as_of_date.strftime("%Y-%m-%d"),),
            )
            start_row = cursor.fetchone()

            # Get price at target_date
            cursor.execute(
                """
                SELECT value FROM pit_data
                WHERE symbol = 'NIFTY50' AND metric_name = 'price'
                AND as_of_date >= ? AND value IS NOT NULL
                ORDER BY as_of_date ASC LIMIT 1
                """,
                (target_date.strftime("%Y-%m-%d"),),
            )
            end_row = cursor.fetchone()

            if start_row and end_row and float(start_row[0]) > 0:
                return (float(end_row[0]) - float(start_row[0])) / float(start_row[0])
    except Exception:
        pass
    return None


def run_portfolio_backtest(
    top_n: int = 20,
    forward_months: int = 6,
    multibagger_threshold: float = 0.30,
    min_quarters: int = 4,
) -> BacktestReport:
    """Run the time-machine portfolio backtest.

    For each quarter in the PIT data:
    1. Rank stocks by score as-of that quarter
    2. Take top-N picks
    3. Measure their actual forward returns
    4. Compute hit rate, multibagger rate, and benchmark comparison

    Args:
        top_n: Number of top picks per quarter.
        forward_months: Forward return horizon.
        multibagger_threshold: Return threshold for "multibagger" label.
        min_quarters: Minimum quarters with picks required.

    Returns:
        BacktestReport with per-quarter and aggregate results.
    """
    _log.info(
        "Starting portfolio backtest",
        top_n=top_n,
        forward_months=forward_months,
    )

    pit_df = _load_pit_data()
    if pit_df.empty:
        return BacktestReport(status="SKIPPED", reason="No PIT data available")

    # Group by quarter
    pit_df["quarter"] = pit_df["as_of_date"].dt.to_period("Q")
    quarters = sorted(pit_df["quarter"].unique())

    if len(quarters) < min_quarters:
        return BacktestReport(
            status="SKIPPED",
            reason=f"Only {len(quarters)} quarters available, need {min_quarters}",
        )

    quarter_results: list[QuarterResult] = []

    for quarter in quarters:
        q_data = pit_df[pit_df["quarter"] == quarter]

        if len(q_data) < top_n:
            continue

        # Rank by score (descending) and take top-N
        q_sorted = q_data.nlargest(top_n, "score")
        quarter_start = quarter.start_time

        # Compute forward returns for each pick
        returns: list[float] = []
        for _, row in q_sorted.iterrows():
            sym = row["symbol"]
            pit_price = row.get("pit_price")
            if pit_price is None or pit_price <= 0:
                continue

            fwd_price = _get_forward_price(sym, quarter_start, forward_months)
            if fwd_price is not None and fwd_price > 0:
                ret = (fwd_price - pit_price) / pit_price
                if np.isfinite(ret):
                    returns.append(ret)

        if not returns:
            continue

        returns_arr = np.array(returns)
        benchmark_ret = _get_benchmark_return(quarter_start, forward_months)

        qr = QuarterResult(
            quarter=str(quarter),
            n_picks=len(returns),
            avg_return=float(np.mean(returns_arr)),
            median_return=float(np.median(returns_arr)),
            hit_rate=float(np.mean(returns_arr > 0) * 100),
            multibagger_rate=float(np.mean(returns_arr > multibagger_threshold) * 100),
            max_return=float(np.max(returns_arr)),
            min_return=float(np.min(returns_arr)),
            benchmark_return=benchmark_ret,
        )
        quarter_results.append(qr)

        _log.info(
            "Quarter backtest complete",
            quarter=str(quarter),
            picks=len(returns),
            avg_return=round(qr.avg_return or 0, 3),
            hit_rate=round(qr.hit_rate or 0, 1),
            multibagger_rate=round(qr.multibagger_rate or 0, 1),
        )

    if not quarter_results:
        return BacktestReport(
            status="SKIPPED",
            reason="No quarters had sufficient data for forward returns",
        )

    # Aggregate stats
    hit_rates = [q.hit_rate for q in quarter_results if q.hit_rate is not None]
    mb_rates = [q.multibagger_rate for q in quarter_results if q.multibagger_rate is not None]
    avg_returns = [q.avg_return for q in quarter_results if q.avg_return is not None]
    excess_returns = [
        (q.avg_return or 0) - (q.benchmark_return or 0)
        for q in quarter_results
        if q.avg_return is not None
    ]

    report = BacktestReport(
        status="OK",
        total_quarters=len(quarter_results),
        avg_hit_rate=float(np.mean(hit_rates)) if hit_rates else None,
        avg_multibagger_rate=float(np.mean(mb_rates)) if mb_rates else None,
        avg_return=float(np.mean(avg_returns)) if avg_returns else None,
        avg_excess_return=float(np.mean(excess_returns)) if excess_returns else None,
        quarters=quarter_results,
    )

    _log.info(
        "Portfolio backtest complete",
        quarters=report.total_quarters,
        avg_hit_rate=round(report.avg_hit_rate or 0, 1),
        avg_multibagger_rate=round(report.avg_multibagger_rate or 0, 1),
        avg_return=round(report.avg_return or 0, 3),
        avg_excess_return=round(report.avg_excess_return or 0, 3),
    )

    # Persist report
    _save_report(report)
    return report


def _save_report(report: BacktestReport) -> None:
    """Save backtest report to runtime directory."""
    path = os.path.join("runtime", "models", "portfolio_backtest.json")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2, default=str)
        _log.info("Backtest report saved", path=path)
    except Exception as exc:
        _log.warning("Could not save backtest report", error=str(exc))


def load_report() -> dict | None:
    """Load persisted backtest report."""
    path = os.path.join("runtime", "models", "portfolio_backtest.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run portfolio backtest")
    parser.add_argument("--top-n", type=int, default=20, help="Top N picks per quarter")
    parser.add_argument("--months", type=int, default=6, help="Forward return horizon")
    parser.add_argument("--threshold", type=float, default=0.30, help="Multibagger threshold")
    args = parser.parse_args()

    result = run_portfolio_backtest(
        top_n=args.top_n,
        forward_months=args.months,
        multibagger_threshold=args.threshold,
    )

    print(json.dumps(result.to_dict(), indent=2, default=str))
