from typing import Any, cast
import numpy as np
import pandas as pd
import vectorbt as vbt
import yfinance as yf
import sqlite3
import os


TRANSACTION_COST = 0.006
DEFAULT_BENCHMARK_SYMBOL = "^CNX500"
DEFAULT_WALK_FORWARD_FEATURES = [
    "score",
    "sales_cagr_5y",
    "avg_roe_5y",
    "pe_ratio",
    "debt_equity",
    "cfo_pat_ratio",
    "market_cap_cr",
    "ret_1m",
    "ret_3m",
    "ret_6m",
    "vol_breakout",
    "dist_from_52w_high",
    "roce",
]


def _canonical_symbol(symbol: str) -> str:
    text = str(symbol).strip().upper()
    if not text:
        return ""
    if text.endswith((".NS", ".BO")):
        return text
    return f"{text}.NS"


def _annualized_return_pct(period_returns: pd.Series, periods_per_year: int = 12) -> float:
    returns = pd.to_numeric(period_returns, errors="coerce").dropna()
    if returns.empty:
        return 0.0
    total_return = float(np.prod(1 + returns))
    if not np.isfinite(total_return) or total_return <= 0:
        return 0.0
    return (total_return ** (periods_per_year / len(returns)) - 1) * 100


def benchmark_metrics(strategy_returns: pd.Series, benchmark_returns: pd.Series) -> dict:
    """
    Compare strategy returns against the benchmark on matching periods.

    Returns percentage fields for CAGR, monthly alpha, tracking error, and a
    unitless beta/information ratio. Empty or non-overlapping benchmark data is
    explicit in `benchmark_status` so consumers do not mistake zeros for truth.
    """
    if benchmark_returns is None or benchmark_returns.empty:
        return {
            "benchmark_cagr": 0.0,
            "alpha_cagr": 0.0,
            "alpha_monthly": 0.0,
            "beta": 0.0,
            "tracking_error": 0.0,
            "information_ratio": 0.0,
            "benchmark_status": "NO_DATA",
        }

    aligned = pd.DataFrame(
        {
            "strategy": pd.to_numeric(strategy_returns, errors="coerce"),
            "benchmark": pd.to_numeric(benchmark_returns, errors="coerce"),
        }
    ).dropna()
    if aligned.empty:
        return {
            "benchmark_cagr": 0.0,
            "alpha_cagr": 0.0,
            "alpha_monthly": 0.0,
            "beta": 0.0,
            "tracking_error": 0.0,
            "information_ratio": 0.0,
            "benchmark_status": "NO_OVERLAP",
        }

    strategy_cagr = _annualized_return_pct(aligned["strategy"])
    benchmark_cagr = _annualized_return_pct(aligned["benchmark"])
    alpha_monthly = float(aligned["strategy"].mean() - aligned["benchmark"].mean())
    excess_returns = aligned["strategy"] - aligned["benchmark"]
    tracking_error = float(excess_returns.std(ddof=1) * np.sqrt(12)) if len(aligned) > 1 else 0.0

    benchmark_var = float(aligned["benchmark"].var(ddof=1)) if len(aligned) > 1 else 0.0
    if benchmark_var > 0:
        beta = float(np.cov(aligned["strategy"], aligned["benchmark"])[0, 1] / benchmark_var)
    else:
        beta = 0.0

    information_ratio = (alpha_monthly * 12 / tracking_error) if tracking_error > 0 else 0.0

    return {
        "benchmark_cagr": benchmark_cagr,
        "alpha_cagr": strategy_cagr - benchmark_cagr,
        "alpha_monthly": alpha_monthly * 100,
        "beta": beta,
        "tracking_error": tracking_error * 100,
        "information_ratio": information_ratio,
        "benchmark_status": "OK",
    }


def _max_drawdown_pct(period_returns: pd.Series) -> float:
    returns = pd.to_numeric(period_returns, errors="coerce").dropna()
    if returns.empty:
        return 0.0
    cum_returns = (1 + returns).cumprod()
    drawdown = cum_returns / cum_returns.cummax() - 1
    return float(drawdown.min() * 100)


def _sharpe_ratio(period_returns: pd.Series, periods_per_year: int = 12) -> float:
    returns = pd.to_numeric(period_returns, errors="coerce").dropna()
    if len(returns) < 2 or returns.std() <= 0:
        return 0.0
    return float((returns.mean() / returns.std()) * np.sqrt(periods_per_year))


def _clean_metrics(metrics: dict) -> dict:
    cleaned = {}
    for key, value in metrics.items():
        if isinstance(value, (int, float, np.number)):
            cleaned[key] = float(value) if np.isfinite(value) else 0.0
        else:
            cleaned[key] = value
    return cleaned


def apply_transaction_costs(
    gross_returns: pd.Series,
    turnover: pd.Series | float,
    transaction_cost: float = TRANSACTION_COST,
) -> pd.Series:
    """
    Subtract monthly turnover cost from gross returns.

    `transaction_cost` is the full round-trip cost paid for the replaced
    fraction of the portfolio. The default 0.6% reflects Indian equity
    brokerage, STT, fees, and typical impact cost.
    """
    returns = pd.to_numeric(gross_returns, errors="coerce").copy()
    if isinstance(turnover, pd.Series):
        turnover_series = pd.to_numeric(turnover, errors="coerce").reindex(returns.index).fillna(0.0)
    else:
        turnover_series = pd.Series(float(turnover), index=returns.index)
    return returns - turnover_series.clip(lower=0.0, upper=1.0) * float(transaction_cost)


def _entry_turnover(position: pd.Series) -> pd.Series:
    """Return 1.0 on months where a position is opened, otherwise 0.0."""
    held = position.fillna(False).astype(bool).astype(float)
    if held.empty:
        return held
    entries = held.diff().fillna(held.iloc[0]).clip(lower=0.0)
    return entries


def _extract_close_series(df: pd.DataFrame, symbol: str, *, single_symbol: bool = False) -> pd.Series:
    if df is None or df.empty:
        return pd.Series(dtype=float)
    if isinstance(df.columns, pd.MultiIndex):
        if (symbol, "Close") in df.columns:
            return pd.to_numeric(df[(symbol, "Close")], errors="coerce")
        if ("Close", symbol) in df.columns:
            return pd.to_numeric(df[("Close", symbol)], errors="coerce")
        if symbol in df.columns.get_level_values(0):
            candidate = df[symbol]
            if isinstance(candidate, pd.DataFrame) and "Close" in candidate.columns:
                return pd.to_numeric(candidate["Close"], errors="coerce")
    elif single_symbol and "Close" in df.columns:
        return pd.to_numeric(df["Close"], errors="coerce")
    elif "Close" in df:
        return pd.to_numeric(df["Close"], errors="coerce")
    return pd.Series(dtype=float)


def _normalise_rebalance_frequency(rebalance_frequency: str) -> str:
    text = str(rebalance_frequency or "Q").strip().upper()
    if text in {"M", "MS", "ME", "MONTH", "MONTHLY"}:
        return "M"
    if text in {"Q", "QS", "QE", "QUARTER", "QUARTERLY"}:
        return "Q"
    raise ValueError("rebalance_frequency must be 'M'/'monthly' or 'Q'/'quarterly'")


def _forward_period_returns(prices: pd.DataFrame | pd.Series, frequency: str):
    if prices is None or prices.empty:
        return pd.Series(dtype=float) if isinstance(prices, pd.Series) else pd.DataFrame()
    period_prices = prices.sort_index().groupby(prices.sort_index().index.to_period(frequency)).last()
    return period_prices.pct_change().shift(-1).dropna(how="all")


def _portfolio_turnover(previous_symbols: set[str], current_symbols: set[str]) -> float:
    if not current_symbols:
        return 0.0
    if not previous_symbols:
        return 1.0
    previous_weight = {symbol: 1.0 / len(previous_symbols) for symbol in previous_symbols}
    current_weight = {symbol: 1.0 / len(current_symbols) for symbol in current_symbols}
    all_symbols = previous_symbols | current_symbols
    turnover = 0.5 * sum(
        abs(current_weight.get(symbol, 0.0) - previous_weight.get(symbol, 0.0))
        for symbol in all_symbols
    )
    return float(min(max(turnover, 0.0), 1.0))


def _walk_forward_feature_columns() -> list[str]:
    try:
        from modules.hybrid_scoring import FEATURES

        return list(FEATURES)
    except Exception:
        return DEFAULT_WALK_FORWARD_FEATURES.copy()


def _sanitize_walk_forward_features(df: pd.DataFrame) -> pd.DataFrame:
    try:
        from modules.hybrid_scoring import _sanitize_features

        return _sanitize_features(df)
    except Exception:
        out = df.copy()
        for col in _walk_forward_feature_columns():
            if col not in out.columns:
                out[col] = 0.0
            out[col] = pd.to_numeric(out[col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return out[_walk_forward_feature_columns()]


def _make_walk_forward_model():
    from modules.hybrid_scoring import _make_xgb_regressor

    return _make_xgb_regressor()


class VectorBTEngine:
    def __init__(
        self,
        period="5y",
        transaction_cost: float = TRANSACTION_COST,
        benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    ):
        self.period = period
        self.transaction_cost = float(transaction_cost)
        self.benchmark_symbol = benchmark_symbol
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

    def run_walk_forward_strategy_backtest(
        self,
        symbols: list,
        min_train_periods: int = 12,
        rebalance_frequency: str = "Q",
        top_quantile: float = 0.8,
        max_positions: int | None = None,
    ) -> dict:
        """
        Expanding-window portfolio backtest using PIT fundamentals only.

        For each test period, the model is fit on periods strictly before that
        test period, ranks the period's universe, buys the top slice equal
        weight, charges turnover-based transaction costs, and compares the
        resulting portfolio stream to the configured benchmark.
        """
        try:
            frequency = _normalise_rebalance_frequency(rebalance_frequency)
            periods_per_year = 12 if frequency == "M" else 4
            clean_symbols = [_canonical_symbol(s) for s in symbols if isinstance(s, str) and str(s).strip()]
            clean_symbols = sorted({s for s in clean_symbols if s})
            if not clean_symbols:
                return {"status": "NO_SYMBOLS", "folds": 0}

            feature_cols = _walk_forward_feature_columns()
            columns = ["symbol", "as_of_date", *feature_cols]
            try:
                conn = sqlite3.connect(self.db_path)
                query = "SELECT {cols} FROM fundamentals_pit WHERE symbol IN ({seq})".format(
                    cols=", ".join(columns),
                    seq=",".join(["?"] * len(clean_symbols)),
                )
                pit_df = pd.read_sql_query(query, conn, params=clean_symbols)
                conn.close()
            except Exception as e:
                print(f"[VectorBT] Error reading PIT features: {e}")
                return {"status": f"DB_ERROR: {str(e)}", "folds": 0}

            if pit_df.empty:
                return {"status": "NO_PIT_DATA", "folds": 0}

            download_symbols = clean_symbols.copy()
            if self.benchmark_symbol and self.benchmark_symbol not in download_symbols:
                download_symbols.append(self.benchmark_symbol)

            print(
                "[VectorBT] Downloading prices for walk-forward portfolio "
                f"({len(download_symbols)} symbols)..."
            )
            raw_prices = yf.download(
                download_symbols,
                period=self.period,
                interval="1mo",
                progress=False,
                group_by="ticker",
            )
            if raw_prices is None or raw_prices.empty:
                return {"status": "NO_PRICE_DATA", "folds": 0}

            close_prices = {}
            is_single = len(download_symbols) == 1
            for sym in clean_symbols:
                close = _extract_close_series(raw_prices, sym, single_symbol=is_single).dropna()
                if not close.empty:
                    close_prices[sym] = close

            if not close_prices:
                return {"status": "INSUFFICIENT_PRICE_DATA", "folds": 0}

            price_matrix = pd.DataFrame(close_prices).sort_index()
            period_returns = _forward_period_returns(price_matrix, frequency)
            if period_returns.empty:
                return {"status": "NO_FORWARD_RETURNS", "folds": 0}

            benchmark_close = (
                _extract_close_series(raw_prices, self.benchmark_symbol, single_symbol=False).dropna()
                if self.benchmark_symbol
                else pd.Series(dtype=float)
            )
            benchmark_returns = _forward_period_returns(benchmark_close, frequency)

            pit_df = pit_df.copy()
            pit_df["symbol"] = pit_df["symbol"].map(_canonical_symbol)
            pit_df["as_of_date"] = pd.to_datetime(pit_df["as_of_date"], errors="coerce")
            pit_df = pit_df.dropna(subset=["symbol", "as_of_date"])
            if pit_df.empty:
                return {"status": "NO_VALID_PIT_DATES", "folds": 0}

            for col in feature_cols:
                if col not in pit_df.columns:
                    pit_df[col] = 0.0
                pit_df[col] = pd.to_numeric(pit_df[col], errors="coerce").replace(
                    [np.inf, -np.inf], np.nan
                )

            pit_df["period"] = pit_df["as_of_date"].dt.to_period(frequency)
            pit_df = (
                pit_df.sort_values("as_of_date")
                .groupby(["period", "symbol"], as_index=False)
                .tail(1)
            )

            def _lookup_forward_return(row):
                period = row["period"]
                symbol = row["symbol"]
                if period not in period_returns.index or symbol not in period_returns.columns:
                    return np.nan
                return period_returns.at[period, symbol]

            pit_df["forward_return"] = pit_df.apply(_lookup_forward_return, axis=1)
            labeled = pit_df.dropna(subset=["forward_return"]).copy()
            if labeled.empty:
                return {"status": "NO_LABELED_RETURNS", "folds": 0}

            periods = sorted(labeled["period"].dropna().unique())
            if len(periods) <= min_train_periods:
                return {
                    "status": "INSUFFICIENT_HISTORY",
                    "folds": 0,
                    "available_periods": len(periods),
                    "required_train_periods": int(min_train_periods),
                }

            previous_positions: set[str] = set()
            gross_returns = {}
            net_returns = {}
            turnovers = {}
            folds = []

            for test_period in periods[int(min_train_periods):]:
                train_df = labeled[labeled["period"] < test_period]
                test_df = labeled[labeled["period"] == test_period].copy()
                if train_df.empty or test_df.empty:
                    continue

                train_periods = train_df["period"].nunique()
                if train_periods < min_train_periods:
                    continue

                model = _make_walk_forward_model()
                X_train = _sanitize_walk_forward_features(train_df[feature_cols])
                y_train = pd.to_numeric(train_df["forward_return"], errors="coerce")
                valid_train = y_train.notna()
                X_train = X_train.loc[valid_train]
                y_train = y_train.loc[valid_train]
                if len(X_train) < 2:
                    continue

                model.fit(X_train, y_train)
                X_test = _sanitize_walk_forward_features(test_df[feature_cols])
                test_df["prediction"] = model.predict(X_test)
                test_df = test_df.replace([np.inf, -np.inf], np.nan).dropna(
                    subset=["prediction", "forward_return"]
                )
                if test_df.empty:
                    continue

                ranked = test_df.sort_values("prediction", ascending=False)
                top_count = max(1, int(np.ceil(len(ranked) * (1 - float(top_quantile)))))
                if max_positions is not None:
                    top_count = min(top_count, int(max_positions))
                top_count = min(top_count, len(ranked))
                selected = ranked.head(top_count)
                current_positions = set(selected["symbol"].tolist())
                turnover = _portfolio_turnover(previous_positions, current_positions)
                period_gross_return = float(selected["forward_return"].mean())
                period_net_return = float(
                    apply_transaction_costs(
                        pd.Series([period_gross_return]),
                        turnover,
                        self.transaction_cost,
                    ).iloc[0]
                )

                gross_returns[test_period] = period_gross_return
                net_returns[test_period] = period_net_return
                turnovers[test_period] = turnover
                train_end = max(train_df["period"])
                folds.append(
                    {
                        "test_period": str(test_period),
                        "train_start_period": str(min(train_df["period"])),
                        "train_end_period": str(train_end),
                        "train_rows": int(len(train_df)),
                        "candidate_count": int(len(ranked)),
                        "selected_count": int(len(selected)),
                        "selected_symbols": selected["symbol"].tolist(),
                        "gross_return": period_gross_return,
                        "net_return": period_net_return,
                        "turnover": turnover,
                    }
                )
                previous_positions = current_positions

            if not net_returns:
                return {"status": "NO_VALID_FOLDS", "folds": 0}

            gross_series = pd.Series(gross_returns).sort_index()
            net_series = pd.Series(net_returns).sort_index()
            turnover_series = pd.Series(turnovers).sort_index()

            metrics = benchmark_metrics(net_series, benchmark_returns)
            result = {
                "status": "OK",
                "strategy": "xgboost_walk_forward",
                "rebalance_frequency": frequency,
                "benchmark_symbol": self.benchmark_symbol,
                "folds": int(len(folds)),
                "gross_cagr": _annualized_return_pct(gross_series, periods_per_year),
                "cagr": _annualized_return_pct(net_series, periods_per_year),
                "transaction_cost_drag": _annualized_return_pct(
                    gross_series, periods_per_year
                )
                - _annualized_return_pct(net_series, periods_per_year),
                "win_rate": float((net_series > 0).mean() * 100),
                "max_drawdown": _max_drawdown_pct(net_series),
                "sharpe_ratio": _sharpe_ratio(net_series, periods_per_year),
                "turnover": float(turnover_series.sum()),
                "avg_turnover": float(turnover_series.mean()),
                "top_quantile": float(top_quantile),
                "max_positions": max_positions,
                "fold_details": folds,
            }
            result.update(_clean_metrics(metrics))
            return _clean_metrics(result)

        except Exception as e:
            print(f"[VectorBT] Walk-forward Backtest failed: {e}")
            return {"status": f"WALK_FORWARD_ERROR: {str(e)}", "folds": 0}

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
            download_symbols = clean_symbols.copy()
            if self.benchmark_symbol and self.benchmark_symbol not in download_symbols:
                download_symbols.append(self.benchmark_symbol)
            df = yf.download(
                download_symbols,
                period=self.period,
                interval="1mo",
                progress=False,
                group_by="ticker",
            )
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

            benchmark_close = (
                get_close_series(self.benchmark_symbol).dropna()
                if self.benchmark_symbol
                else pd.Series(dtype=float)
            )
            benchmark_returns = benchmark_close.sort_index().pct_change().shift(-1).dropna()

            if not close_prices:
                return {s: {"symbol": s, "status": "INSUFFICIENT_DATA"} for s in clean_symbols}

            price_matrix = pd.DataFrame(close_prices).sort_index()
            returns = price_matrix.pct_change().shift(-1) # Forward 1-month returns

            results = {}
            # Base metrics fallback
            for sym in clean_symbols:
                status = "OK" if sym in close_prices else "INSUFFICIENT_DATA"
                results[sym] = {
                    "symbol": sym,
                    "cagr": 0.0,
                    "gross_cagr": 0.0,
                    "win_rate": 0.0,
                    "max_drawdown": 0.0,
                    "sharpe_ratio": 0.0,
                    "transaction_cost_drag": 0.0,
                    "turnover": 0.0,
                    "benchmark_symbol": self.benchmark_symbol,
                    "benchmark_cagr": 0.0,
                    "alpha_cagr": 0.0,
                    "alpha_monthly": 0.0,
                    "beta": 0.0,
                    "tracking_error": 0.0,
                    "information_ratio": 0.0,
                    "benchmark_status": "NO_DATA",
                    "status": status,
                }

            if scores_df.empty:
                print("[VectorBT] No historical scores found. Approximating with buy & hold.")
                for sym in price_matrix.columns:
                    monthly_returns = returns[sym].dropna()
                    entry_turnover = pd.Series(0.0, index=monthly_returns.index)
                    if not entry_turnover.empty:
                        entry_turnover.iloc[0] = 1.0
                    net_monthly_returns = apply_transaction_costs(
                        monthly_returns,
                        entry_turnover,
                        self.transaction_cost,
                    )
                    gross_cagr = self._sanitize_metric(
                        _annualized_return_pct(monthly_returns), 0.0
                    )
                    net_cagr = self._sanitize_metric(
                        _annualized_return_pct(net_monthly_returns), 0.0
                    )
                    results[sym]["gross_cagr"] = gross_cagr
                    results[sym]["cagr"] = net_cagr
                    results[sym]["transaction_cost_drag"] = self._sanitize_metric(
                        gross_cagr - net_cagr, 0.0
                    )
                    results[sym]["turnover"] = 1.0
                    metrics = benchmark_metrics(net_monthly_returns, benchmark_returns)
                    results[sym].update(
                        {k: self._sanitize_metric(v, v) if k != "benchmark_status" else v for k, v in metrics.items()}
                    )
                return results

            # 3. Align scores with monthly dates and quintile sort
            scores_df["date"] = pd.to_datetime(scores_df["as_of_date"]).dt.to_period("M")
            scores_df["score"] = pd.to_numeric(scores_df["score"], errors="coerce").fillna(0)

            # Map returns to same monthly period
            returns.index = returns.index.to_period("M")
            if not benchmark_returns.empty:
                benchmark_returns.index = benchmark_returns.index.to_period("M")

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

                position = top_q[sym].reindex(common_dates).fillna(False)
                turnover = _entry_turnover(position)
                selected_returns = sym_returns[position].dropna()
                selected_turnover = turnover.reindex(selected_returns.index).fillna(0.0)
                sym_strat_returns = apply_transaction_costs(
                    selected_returns,
                    selected_turnover,
                    self.transaction_cost,
                ).dropna()

                if len(sym_strat_returns) > 0:
                    gross_cagr = (
                        np.prod(1 + selected_returns) ** (12 / len(selected_returns)) - 1
                    ) * 100
                    cagr = (np.prod(1 + sym_strat_returns) ** (12 / len(sym_strat_returns)) - 1) * 100
                    win_rate = (sym_strat_returns > 0).mean() * 100

                    # Approximated drawdowns & sharpe
                    cum_returns = (1 + sym_strat_returns).cumprod()
                    drawdown = cum_returns / cum_returns.cummax() - 1
                    max_dd = drawdown.min() * 100
                    sharpe = (sym_strat_returns.mean() / sym_strat_returns.std()) * np.sqrt(12) if sym_strat_returns.std() > 0 else 0

                    results[sym]["cagr"] = self._sanitize_metric(cagr, 0.0)
                    results[sym]["gross_cagr"] = self._sanitize_metric(gross_cagr, 0.0)
                    results[sym]["win_rate"] = self._sanitize_metric(win_rate, 0.0)
                    results[sym]["max_drawdown"] = self._sanitize_metric(max_dd, 0.0)
                    results[sym]["sharpe_ratio"] = self._sanitize_metric(sharpe, 0.0)
                    results[sym]["transaction_cost_drag"] = self._sanitize_metric(
                        gross_cagr - cagr, 0.0
                    )
                    results[sym]["turnover"] = self._sanitize_metric(selected_turnover.sum(), 0.0)
                    metrics = benchmark_metrics(sym_strat_returns, benchmark_returns)
                    results[sym].update(
                        {k: self._sanitize_metric(v, v) if k != "benchmark_status" else v for k, v in metrics.items()}
                    )
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
