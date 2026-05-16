from typing import Any, cast
import numpy as np
import pandas as pd
import vectorbt as vbt
import yfinance as yf
import sqlite3
import os

class VectorBTEngine:
    def __init__(self, period="5y"):
        self.period = period
        self.db_path = os.path.join(os.path.dirname(__file__), "..", "runtime", "stocks.db")

    @staticmethod
    def _sanitize_metric(value, default=0.0):
        try:
            val = float(value)
        except (TypeError, ValueError):
            return float(default)
        if np.isnan(val) or np.isinf(val):
            return float(default)
        return float(val)

    def run_batch_momentum_backtest(self, symbols: list) -> dict:
        """
        Runs a fundamental PIT backtest by sorting stocks by their Nexus Alpha score,
        going long the top-quintile, and shorting/avoiding the bottom-quintile.
        (Replaces the old SMA momentum crossover strategy).
        """
        try:
            clean_symbols = [s + ".NS" if not s.endswith((".NS", ".BO")) else s for s in symbols if isinstance(s, str) and s.strip()]
            if not clean_symbols:
                return {}

            print(f"[VectorBT] Fetching fundamental scores for {len(clean_symbols)} tickers...")

            # 1. Fetch historical PIT scores from DB
            try:
                conn = sqlite3.connect(self.db_path)
                query = "SELECT symbol, as_of_date, score FROM fundamentals_pit WHERE symbol IN ({seq})".format(
                    seq=','.join(['?']*len(clean_symbols)))
                scores_df = pd.read_sql_query(query, conn, params=clean_symbols)
                conn.close()
            except Exception as e:
                print(f"[VectorBT] Error reading DB: {e}")
                scores_df = pd.DataFrame(columns=["symbol", "as_of_date", "score"])

            # 2. Fetch historical prices
            print("[VectorBT] Downloading price data...")
            df = yf.download(clean_symbols, period=self.period, interval="1mo", progress=False, group_by="ticker")
            if df.empty:
                return {s: {"symbol": s, "status": "NO_DATA"} for s in clean_symbols}

            # Helper to extract Close price series safely
            def get_close_series(sym):
                if isinstance(df.columns, pd.MultiIndex):
                    if (sym, "Close") in df.columns:
                        return df[(sym, "Close")]
                    if ("Close", sym) in df.columns:
                        return df[("Close", sym)]
                    if sym in df and isinstance(df[sym], pd.DataFrame) and "Close" in df[sym]:
                        return df[sym]["Close"]
                elif "Close" in df:
                    return df["Close"]
                return pd.Series(dtype=float)

            close_prices = {}
            for sym in clean_symbols:
                s_close = get_close_series(sym).dropna()
                if not s_close.empty:
                    close_prices[sym] = s_close

            if not close_prices:
                return {s: {"symbol": s, "status": "INSUFFICIENT_DATA"} for s in clean_symbols}

            price_matrix = pd.DataFrame(close_prices).sort_index()
            returns = price_matrix.pct_change().shift(-1) # Forward 1-month returns

            results = {}
            # Base metrics fallback
            for sym in clean_symbols:
                status = "OK" if sym in close_prices else "INSUFFICIENT_DATA"
                results[sym] = {
                    "symbol": sym, "cagr": 0.0, "win_rate": 0.0,
                    "max_drawdown": 0.0, "sharpe_ratio": 0.0, "status": status
                }

            if scores_df.empty:
                print("[VectorBT] No historical scores found. Approximating with buy & hold.")
                # Fallback to Buy & Hold metric for each
                ann_returns = (price_matrix.iloc[-1] / price_matrix.iloc[0]) ** (12 / len(price_matrix)) - 1
                for sym in price_matrix.columns:
                    results[sym]["cagr"] = self._sanitize_metric(ann_returns.get(sym, 0) * 100, 0.0)
                return results

            # 3. Align scores with monthly dates and quintile sort
            scores_df["date"] = pd.to_datetime(scores_df["as_of_date"]).dt.to_period("M")
            scores_df["score"] = pd.to_numeric(scores_df["score"], errors="coerce").fillna(0)

            # Map returns to same monthly period
            returns.index = returns.index.to_period("M")

            monthly_scores = scores_df.pivot_table(index="date", columns="symbol", values="score", aggfunc="last")

            # Create a continuous monthly period index to forward-fill sparse PIT dates
            if not monthly_scores.empty and not returns.empty:
                min_date = min(monthly_scores.index.min(), returns.index.min())
                max_date = max(monthly_scores.index.max(), returns.index.max())
                all_months = pd.period_range(start=min_date, end=max_date, freq='M')
                monthly_scores = monthly_scores.reindex(all_months).ffill()

            # Align indices
            common_dates = monthly_scores.index.intersection(returns.index)

            for sym in price_matrix.columns:
                if sym not in monthly_scores.columns:
                    continue

                sym_scores = monthly_scores[sym].reindex(common_dates)
                sym_returns = returns[sym].reindex(common_dates)

                row_scores = monthly_scores.reindex(common_dates)
                top_q = row_scores.apply(lambda x: x >= x.quantile(0.8), axis=1)

                sym_strat_returns = sym_returns[top_q[sym]].dropna()

                if len(sym_strat_returns) > 0:
                    cagr = (np.prod(1 + sym_strat_returns) ** (12 / len(sym_strat_returns)) - 1) * 100
                    win_rate = (sym_strat_returns > 0).mean() * 100

                    # Approximated drawdowns & sharpe
                    cum_returns = (1 + sym_strat_returns).cumprod()
                    drawdown = cum_returns / cum_returns.cummax() - 1
                    max_dd = drawdown.min() * 100
                    sharpe = (sym_strat_returns.mean() / sym_strat_returns.std()) * np.sqrt(12) if sym_strat_returns.std() > 0 else 0

                    results[sym]["cagr"] = self._sanitize_metric(cagr, 0.0)
                    results[sym]["win_rate"] = self._sanitize_metric(win_rate, 0.0)
                    results[sym]["max_drawdown"] = self._sanitize_metric(max_dd, 0.0)
                    results[sym]["sharpe_ratio"] = self._sanitize_metric(sharpe, 0.0)
                    results[sym]["status"] = "OK"

            return results

        except Exception as e:
            print(f"[VectorBT] Batch Backtest failed: {e}")
            return {s: {"symbol": s, "status": f"BATCH_ERROR: {str(e)}"} for s in symbols}

if __name__ == "__main__":
    engine = VectorBTEngine(period="5y")
    res = engine.run_batch_momentum_backtest(["SAKSOFT.NS", "TCS.NS"])
    print("\n--- VectorBT Optimization Results ---")
    for sym, r in res.items():
        print(
            f"{sym}: {r.get('cagr')}% CAGR | {r.get('win_rate')}% Win | Status: {r.get('status')}"
        )
