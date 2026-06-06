from pathlib import Path
from typing import Any, cast
import logging
import numpy as np
import pandas as pd
import vectorbt as vbt
import yfinance as yf
import os

from backtest.survivorship_adjusted_loader import SurvivorshipAdjustedLoader

from config import (
    TRANSACTION_COST,
    TC_STT_SELL,
    TC_EXCHANGE,
    TC_SEBI_FEE,
    TC_STAMP_BUY,
    TC_BROKERAGE_PER_SIDE,
    TC_GST_RATE,
    TC_IMPACT_ALPHA,
    TC_ADV_FRAC_LARGE,
    TC_ADV_FRAC_MID,
    TC_ADV_FRAC_SMALL,
)
from core.observability.logger import get_logger
_log = get_logger("backtest.backtest_engine")
RF_ANNUAL = float(os.getenv("RISK_FREE_RATE_ANNUAL", "0.065"))
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

logger = logging.getLogger(__name__)


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
    return (total_return ** (periods_per_year / len(returns)) - 1) * 100  # type: ignore


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


def _sharpe_ratio(
    period_returns: pd.Series,
    periods_per_year: int = 12,
    rf_annual: float = RF_ANNUAL,
) -> float:
    returns = pd.to_numeric(period_returns, errors="coerce").dropna()
    if len(returns) < 2 or returns.std() <= 0:
        return 0.0
    rf_per_period = float(rf_annual) / periods_per_year
    excess = returns - rf_per_period
    return float((excess.mean() / excess.std()) * np.sqrt(periods_per_year))


def _sortino_ratio(
    period_returns: pd.Series,
    periods_per_year: int = 12,
    rf_annual: float = RF_ANNUAL,
) -> float:
    """Sortino ratio: excess return divided by downside deviation only.

    Unlike Sharpe, upside volatility is not penalised. A strategy with large
    positive months (momentum, midcap) is correctly rewarded.

    Returns 0.0 when there are fewer than 3 below-Rf months — downside std
    computed from 1-2 data points is statistically meaningless.
    """
    returns = pd.to_numeric(period_returns, errors="coerce").dropna()
    if len(returns) < 2:
        return 0.0
    rf_per_period = float(rf_annual) / periods_per_year
    excess = returns - rf_per_period
    downside = excess[excess < 0]
    if len(downside) < 3 or downside.std() <= 0:
        return 0.0
    return float((excess.mean() / downside.std()) * np.sqrt(periods_per_year))


def _calmar_ratio(
    period_returns: pd.Series,
    periods_per_year: int = 12,
) -> float:
    """Calmar ratio: annualised CAGR divided by absolute max drawdown.

    Answers: for every 1% of peak-to-trough loss, how much annual return was
    delivered? Calmar of 0.5 = 20% CAGR on 40% drawdown. Higher is better.

    Guard: uses `mdd < 0` (not `!= 0`) to handle flat/monotonic series where
    float arithmetic may produce a tiny positive drawdown value.
    """
    ann_ret = _annualized_return_pct(period_returns, periods_per_year) / 100
    mdd = _max_drawdown_pct(period_returns) / 100
    if mdd >= 0:
        return 0.0
    if not np.isfinite(ann_ret):
        return 0.0
    return float(ann_ret / abs(mdd))


def _clean_metrics(metrics: dict) -> dict:
    cleaned = {}
    for key, value in metrics.items():
        if isinstance(value, int | float | np.number):
            cleaned[key] = float(value) if np.isfinite(value) else 0.0
        else:
            cleaned[key] = value
    return cleaned


def compute_round_trip_cost(
    cap_category: str = "Mid",
    trade_value: float = 1.0,
    adv_30d: float | None = None,
) -> float:
    """Compute the full round-trip transaction cost for an Indian equity trade.

    Components (2025 rates, all expressed as fraction of trade value):
        Buy  side: brokerage + GST on brokerage + stamp duty + exchange + SEBI
        Sell side: brokerage + GST on brokerage + STT + exchange + SEBI
        Both sides: market impact (if adv_30d provided or inferred from cap)

    Args:
        cap_category:  "Large", "Mid", or "Small" (case-insensitive).
                       Used to infer adv_30d when not explicitly provided.
        trade_value:   Order size in rupees. Used only for impact calculation.
                       Relative to adv_30d — can use any consistent unit.
        adv_30d:       30-day avg daily value traded in rupees. When None,
                       inferred from cap_category via TC_ADV_FRAC constants.

    Returns:
        Round-trip cost as a fraction of trade value.
        Typical values (component model, 2025 rates):
          Large cap: ~0.0024 (24 bps)
          Mid cap:   ~0.0048 (48 bps)
          Small cap: ~0.0090 (90 bps)
    """
    cap = str(cap_category).lower()

    # Base charges — direction-asymmetric
    brokerage_gst = TC_BROKERAGE_PER_SIDE * TC_GST_RATE
    buy_side = (
        TC_BROKERAGE_PER_SIDE
        + brokerage_gst
        + TC_STAMP_BUY
        + TC_EXCHANGE
        + TC_SEBI_FEE
    )
    sell_side = (
        TC_BROKERAGE_PER_SIDE
        + brokerage_gst
        + TC_STT_SELL
        + TC_EXCHANGE
        + TC_SEBI_FEE
    )
    base_cost = buy_side + sell_side

    # Market impact — infer ADV from cap category when not provided
    if adv_30d is None or adv_30d <= 0:
        if "large" in cap:
            adv_frac = TC_ADV_FRAC_LARGE
        elif "small" in cap:
            adv_frac = TC_ADV_FRAC_SMALL
        else:                               # mid, unknown, default
            adv_frac = TC_ADV_FRAC_MID
        # adv_30d is estimated as adv_frac × trade_value
        # → sqrt(trade_value / adv_30d) = sqrt(1 / adv_frac)
        impact = TC_IMPACT_ALPHA / (adv_frac ** 0.5)
    else:
        if trade_value <= 0 or not np.isfinite(trade_value):
            impact = 0.0
        else:
            impact = TC_IMPACT_ALPHA * ((trade_value / adv_30d) ** 0.5)

    # Round-trip impact is paid on both entry and exit
    return float(base_cost + 2 * impact)


def cost_breakdown(cap_category: str = "Mid") -> dict[str, float]:
    """Return itemised cost breakdown for documentation and reporting.

    Keys mirror the component names in config.py for traceability.
    All values are fractions of trade value.
    """
    cap = str(cap_category).lower()
    adv_frac = (
        TC_ADV_FRAC_LARGE if "large" in cap else
        TC_ADV_FRAC_SMALL if "small" in cap else
        TC_ADV_FRAC_MID
    )
    impact_one_way = TC_IMPACT_ALPHA / (adv_frac ** 0.5)
    return {
        "brokerage_per_side": TC_BROKERAGE_PER_SIDE,
        "gst_on_brokerage_per_side": TC_BROKERAGE_PER_SIDE * TC_GST_RATE,
        "stt_sell":          TC_STT_SELL,
        "exchange_per_side": TC_EXCHANGE,
        "sebi_fee_per_side": TC_SEBI_FEE,
        "stamp_duty_buy":    TC_STAMP_BUY,
        "impact_per_way":    impact_one_way,
        "total_round_trip":  compute_round_trip_cost(cap_category),
    }


def apply_transaction_costs(
    gross_returns: pd.Series,
    turnover: pd.Series | float,
    transaction_cost: float | None = None,
    cap_category: str = "Mid",
) -> pd.Series:
    """Subtract period transaction costs from gross returns.

    When `transaction_cost` is None (recommended), the cost is computed
    from the component model via `compute_round_trip_cost(cap_category)`.
    When provided explicitly (legacy / test override), that value is used
    directly — enabling backward-compat and per-symbol overrides.

    Args:
        gross_returns:    Period gross return series.
        turnover:         Portfolio turnover series or scalar (0–1 fraction).
        transaction_cost: Override cost as fraction of trade value. Pass None
                          to use the component model (recommended).
        cap_category:     "Large", "Mid", or "Small". Used by component model.

    The deduction each period is: turnover × round_trip_cost.
    Turnover is clipped to [0, 1] — full portfolio replacement costs one
    full round-trip, partial replacement costs proportionally less.
    """
    if transaction_cost is None:
        cost = compute_round_trip_cost(cap_category)
    else:
        cost = float(transaction_cost)

    returns = pd.to_numeric(gross_returns, errors="coerce").copy()
    if isinstance(turnover, pd.Series):
        turnover_series = (
            pd.to_numeric(turnover, errors="coerce")
            .reindex(returns.index)
            .fillna(0.0)
        )
    else:
        turnover_series = pd.Series(float(turnover), index=returns.index)

    return returns - turnover_series.clip(lower=0.0, upper=1.0) * cost


def _entry_turnover(position: pd.Series) -> pd.Series:
    """Return 1.0 on months where a position is opened, otherwise 0.0."""
    held = position.fillna(False).astype(bool).astype(float)
    if held.empty:
        return held
    entries = held.diff().fillna(held.iloc[0]).clip(lower=0.0)
    return entries


def _extract_close_series(df: pd.DataFrame, symbol: str, *, single_symbol: bool = False) -> pd.Series:
    """
    Extract adjusted close prices from a yfinance download.

    All engine downloads call yfinance with auto_adjust=True, so the "Close"
    field is already split/dividend-adjusted. Do not switch this to raw close
    without also changing return calculations and tests.
    """
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
    # Forward label semantics: period T score maps to period T+1 return.
    # shift(-1) intentionally leaves the latest period unlabeled, and dropna
    # removes that row so the backtest never scores a period with no future return.
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
    _survivorship_warning_emitted = False

    def __init__(
        self,
        period="5y",
        transaction_cost: float | None = None,
        benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
        cap_category: str = "Mid",
    ):
        self.period = period
        self.cap_category = cap_category
        self.transaction_cost = transaction_cost if transaction_cost is None else float(transaction_cost)
        self.benchmark_symbol = benchmark_symbol
        self.db_path = os.path.join(os.path.dirname(__file__), "..", "runtime", "stocks.db")
        # Resolve data dir using the same logic as _warn_if_survivorship_metadata_missing
        project_data = Path(__file__).resolve().parents[1] / "data"
        self._survivorship_loader = SurvivorshipAdjustedLoader(
            data_dir=str(project_data)
        )
        self._warn_if_survivorship_metadata_missing()

    def _warn_if_survivorship_metadata_missing(self) -> None:
        if VectorBTEngine._survivorship_warning_emitted:
            return

        project_data = Path(__file__).resolve().parents[1] / "data"
        cwd_data = Path("data")
        data_dirs = [project_data]
        if cwd_data.resolve() != project_data.resolve():
            data_dirs.append(cwd_data)

        has_metadata = any(
            (data_dir / "nse_listing_dates.csv").exists()
            or any(data_dir.glob("nifty500_*.csv"))
            for data_dir in data_dirs
        )
        if not has_metadata:
            logger.warning(
                "SURVIVORSHIP BIAS: No listing/delisting data found. "
                "Backtest returns will be overstated. "
                "See backtest/survivorship_adjusted_loader.py."
            )
        VectorBTEngine._survivorship_warning_emitted = True

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
                from db.db_core import get_db_connection
                from sqlalchemy import text
                seq_placeholders = ", ".join([f":s{idx}" for idx in range(len(clean_symbols))])
                query = "SELECT {cols} FROM fundamentals_pit WHERE symbol IN ({seq})".format(
                    cols=", ".join(columns),
                    seq=seq_placeholders,
                )
                params = {f"s{idx}": s for idx, s in enumerate(clean_symbols)}
                with get_db_connection() as conn:
                    pit_df = pd.read_sql_query(text(query), conn, params=params)
            except Exception as e:
                _log.error(f"[VectorBT] Error reading PIT features: {e}")
                return {"status": f"DB_ERROR: {str(e)}", "folds": 0}

            if pit_df.empty:
                return {"status": "NO_PIT_DATA", "folds": 0}

            download_symbols = clean_symbols.copy()
            if self.benchmark_symbol and self.benchmark_symbol not in download_symbols:
                download_symbols.append(self.benchmark_symbol)

            _log.info("[VectorBT] Downloading prices for walk-forward portfolio "
                f"({len(download_symbols)} symbols)...")
            raw_prices = yf.download(
                download_symbols,
                period=self.period,
                interval="1mo",
                progress=False,
                group_by="ticker",
                auto_adjust=True,
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

                # ── Survivorship filter: exclude delisted/unlisted stocks ──
                period_date = str(test_period.start_time.date())
                test_symbols_bare = [
                    s.replace(".NS", "").replace(".BO", "")
                    for s in test_df["symbol"].unique()
                ]
                valid_bare = self._survivorship_loader.get_universe(
                    as_of_date=period_date,
                    candidates=test_symbols_bare,
                )
                valid_canonical = {_canonical_symbol(s) for s in valid_bare}
                test_df = test_df[test_df["symbol"].isin(valid_canonical)]
                if test_df.empty:
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
                        transaction_cost=self.transaction_cost,
                        cap_category=self.cap_category,
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
                "sortino_ratio": _sortino_ratio(net_series, periods_per_year),
                "calmar_ratio": _calmar_ratio(net_series, periods_per_year),
                "turnover": float(turnover_series.sum()),
                "avg_turnover": float(turnover_series.mean()),
                "top_quantile": float(top_quantile),
                "max_positions": max_positions,
                "fold_details": folds,
            }
            result.update(_clean_metrics(metrics))
            return _clean_metrics(result)

        except Exception as e:
            _log.error(f"[VectorBT] Walk-forward Backtest failed: {e}")
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

            _log.info(f"[VectorBT] Fetching fundamental scores for {len(clean_symbols)} tickers...")

            # 1. Fetch historical PIT scores from DB
            try:
                from db.db_core import get_db_connection
                from sqlalchemy import text
                seq_placeholders = ", ".join([f":s{idx}" for idx in range(len(clean_symbols))])
                query = f"SELECT symbol, as_of_date, score FROM fundamentals_pit WHERE symbol IN ({seq_placeholders})"
                params = {f"s{idx}": s for idx, s in enumerate(clean_symbols)}
                with get_db_connection() as conn:
                    scores_df = pd.read_sql_query(text(query), conn, params=params)
            except Exception as e:
                _log.error(f"[VectorBT] Error reading DB: {e}")
                scores_df = pd.DataFrame(columns=["symbol", "as_of_date", "score"])

            # 2. Fetch historical prices
            _log.info("[VectorBT] Downloading price data...")
            download_symbols = clean_symbols.copy()
            if self.benchmark_symbol and self.benchmark_symbol not in download_symbols:
                download_symbols.append(self.benchmark_symbol)
            df = yf.download(
                download_symbols,
                period=self.period,
                interval="1mo",
                progress=False,
                group_by="ticker",
                auto_adjust=True,
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
            # Forward benchmark labels: the latest month is dropped because it has
            # no realized next-month return, matching the stock return labels.
            benchmark_returns = benchmark_close.sort_index().pct_change().shift(-1).dropna()

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
                    "sortino_ratio": 0.0,
                    "calmar_ratio": 0.0,
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

            if not close_prices:
                return results

            price_matrix = pd.DataFrame(close_prices).sort_index()
            # Forward 1-month labels: period T score maps to period T+1 return.
            # The final month remains NaN after shift(-1) and is excluded when
            # each symbol's return series is dropna()'d below.
            returns = price_matrix.pct_change().shift(-1)

            if scores_df.empty:
                _log.info("[VectorBT] No historical scores found. Approximating with buy & hold.")
                for sym in price_matrix.columns:
                    monthly_returns = returns[sym].dropna()
                    entry_turnover = pd.Series(0.0, index=monthly_returns.index)
                    if not entry_turnover.empty:
                        entry_turnover.iloc[0] = 1.0
                    net_monthly_returns = apply_transaction_costs(
                        monthly_returns,
                        entry_turnover,
                        transaction_cost=self.transaction_cost,
                        cap_category=self.cap_category,
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
                    results[sym]["sharpe_ratio"] = self._sanitize_metric(
                        _sharpe_ratio(net_monthly_returns), 0.0
                    )
                    results[sym]["sortino_ratio"] = self._sanitize_metric(
                        _sortino_ratio(net_monthly_returns), 0.0
                    )
                    results[sym]["calmar_ratio"] = self._sanitize_metric(
                        _calmar_ratio(net_monthly_returns), 0.0
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

            # ── Survivorship filter: mask scores of delisted/unlisted stocks ──
            # Build a boolean mask (month × symbol) where True = valid at that date
            survivorship_mask = pd.DataFrame(
                False,
                index=common_dates,
                columns=monthly_scores.columns,
            )
            for period in common_dates:
                period_date = str(period.start_time.date())
                syms_bare = [
                    s.replace(".NS", "").replace(".BO", "")
                    for s in monthly_scores.columns
                ]
                valid_bare = set(
                    self._survivorship_loader.get_universe(
                        as_of_date=period_date,
                        candidates=syms_bare,
                    )
                )
                for sym_canonical in monthly_scores.columns:
                    bare = sym_canonical.replace(".NS", "").replace(".BO", "")
                    if bare in valid_bare:
                        survivorship_mask.at[period, sym_canonical] = True

            # Apply mask: NaN out scores for stocks not in the valid universe
            filtered_scores = monthly_scores.reindex(common_dates).where(survivorship_mask)

            for sym in price_matrix.columns:
                if sym not in filtered_scores.columns:
                    continue

                sym_scores = filtered_scores[sym].reindex(common_dates)
                sym_returns = returns[sym].reindex(common_dates)

                row_scores = filtered_scores.reindex(common_dates)
                top_q = row_scores.apply(lambda x: x >= x.quantile(0.8), axis=1)

                position = top_q[sym].reindex(common_dates).fillna(False)
                turnover = _entry_turnover(position)
                selected_returns = sym_returns[position].dropna()
                selected_turnover = turnover.reindex(selected_returns.index).fillna(0.0)
                sym_strat_returns = apply_transaction_costs(
                    selected_returns,
                    selected_turnover,
                    transaction_cost=self.transaction_cost,
                    cap_category=self.cap_category,
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
                    sharpe = _sharpe_ratio(sym_strat_returns)

                    sortino = _sortino_ratio(sym_strat_returns)
                    calmar = _calmar_ratio(sym_strat_returns)

                    results[sym]["cagr"] = self._sanitize_metric(cagr, 0.0)
                    results[sym]["gross_cagr"] = self._sanitize_metric(gross_cagr, 0.0)
                    results[sym]["win_rate"] = self._sanitize_metric(win_rate, 0.0)
                    results[sym]["max_drawdown"] = self._sanitize_metric(max_dd, 0.0)
                    results[sym]["sharpe_ratio"] = self._sanitize_metric(sharpe, 0.0)
                    results[sym]["sortino_ratio"] = self._sanitize_metric(sortino, 0.0)
                    results[sym]["calmar_ratio"] = self._sanitize_metric(calmar, 0.0)
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
            _log.error(f"[VectorBT] Batch Backtest failed: {e}")
            return {s: {"symbol": s, "status": f"BATCH_ERROR: {str(e)}"} for s in symbols}

if __name__ == "__main__":
    engine = VectorBTEngine(period="5y")
    res = engine.run_batch_momentum_backtest(["SAKSOFT.NS", "TCS.NS"])
    _log.info("\n--- VectorBT Optimization Results ---")
    for sym, r in res.items():
        _log.info(f"{sym}: {r.get('cagr')}% CAGR | {r.get('win_rate')}% Win | Status: {r.get('status')}")
