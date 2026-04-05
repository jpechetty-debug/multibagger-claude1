# backtest_qarp.py
import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TextColumn, BarColumn, TimeRemainingColumn

# Ensure project modules are importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ticker_list import TICKERS
from db.repository import get_connection
from modules.scoring import calculate_institutional_score
from modules.fundamentals import calculate_piotroski_f_score
from modules.regime_hmm import RegimeHMM
import config

# Disable emojis for Windows terminal stability
console = Console(force_terminal=True, emoji=False)

def print_header(text):
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f" [bold white]{text}[/bold white]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")

def get_pit_factors(symbol, target_date, cache=None):
    try:
        if cache and symbol in cache:
            ticker = cache[symbol]
        else:
            ticker = yf.Ticker(symbol)
            if cache is not None: cache[symbol] = ticker

        income = ticker.quarterly_income_stmt
        balance = ticker.quarterly_balance_sheet
        cashflow = ticker.quarterly_cashflow
        
        if income.empty or balance.empty:
            return None
            
        reporting_lag = pd.Timedelta(days=90)
        dates = pd.to_datetime(income.columns)
        available_quarters = [d for d in dates if (d + reporting_lag) <= pd.to_datetime(target_date)]
        
        if not available_quarters:
            return None
            
        latest_q = available_quarters[0]
        hist_1y = ticker.history(start=target_date - timedelta(days=365), end=target_date)
        if hist_1y.empty:
            return None
            
        p_now = float(hist_1y['Close'].iloc[-1])
        high_52w = float(hist_1y['High'].max())
        down_from_high = (high_52w - p_now) / high_52w if high_52w > 0 else 0
        atr_14 = (hist_1y['High'] - hist_1y['Low']).tail(14).mean()
        
        data = {
            "Symbol": symbol,
            "Price": p_now,
            "Sector": ticker.info.get('sector', 'Unknown'),
            "Sales_Growth_5Y%": 0,
            "ROE%": 0,
            "CFO_PAT_Ratio": 0,
            "Debt_Equity": 0,
            "F_Score": calculate_piotroski_f_score(ticker),
            "Down_From_52W_High%": down_from_high * 100,
            "ATR": atr_14,
            "Market_Cap": ticker.info.get('marketCap', 1e8),
            "RS_Rating": 1.0
        }
        
        # Calculate ratios
        rev = income[latest_q].get('Total Revenue', 0)
        dates = pd.to_datetime(income.columns)
        prev_q = dates[1] if len(dates) > 1 else None
        rev_prev = income[prev_q].get('Total Revenue', 0) if prev_q else 0
        data["Sales_Growth_TTM%"] = ((rev - rev_prev) / rev_prev * 100) if rev_prev > 0 else 0
        
        net_income = income[latest_q].get('Net Income', 0)
        equity = balance[latest_q].get('Stockholders Equity', 1)
        total_debt = balance[latest_q].get('Total Debt', 0)
        cfo = cashflow[latest_q].get('Operating Cash Flow', 0)
        
        data["ROE%"] = (net_income / equity) * 100 if equity > 0 else 0
        data["CFO_PAT_Ratio"] = cfo / net_income if net_income > 0 else 1.0
        data["Debt_Equity"] = total_debt / equity if equity > 0 else 0
        
        return data
    except Exception:
        return None

def calculate_risk_metrics(rets, bench_rets=None):
    if len(rets) < 2: return {}
    total_ret = (np.prod(1 + np.array(rets) / 100) - 1)
    ann_ret = (1 + total_ret) ** (4 / len(rets)) - 1
    vol = (np.std(rets) / 100) * np.sqrt(4)
    sharpe = ann_ret / vol if vol > 0 else 0
    cum_rets = np.cumprod(1 + np.array(rets) / 100)
    peak = np.maximum.accumulate(cum_rets)
    dd = (cum_rets - peak) / peak
    mdd = np.min(dd)
    calmar = ann_ret / abs(mdd) if mdd < 0 else 0
    metrics = {"CAGR": ann_ret * 100, "Vol": vol * 100, "Sharpe": sharpe, "MaxDD": mdd * 100, "Calmar": calmar}
    if bench_rets is not None:
        tracking_error = (np.std(np.array(rets) - np.array(bench_rets)) / 100) * np.sqrt(4)
        alpha = (ann_ret - ((1 + (np.prod(1 + np.array(bench_rets) / 100) - 1)) ** (4/len(rets)) - 1))
        metrics["Alpha"] = alpha * 100
        metrics["IR"] = alpha / tracking_error if tracking_error > 0 else 0
    return metrics

def run_backtest(years=3, universe_size=50, stress_mode=False, rebal_freq='MS'):
    print_header(f"Sovereign QARP Institutional Validation ({'STRESS ' if stress_mode else ''}{years}Y)")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    reb_dates = pd.date_range(start=start_date, end=end_date, freq=rebal_freq)
    portfolio_value = 100.0
    history = []
    ticker_cache = {}
    hmm = RegimeHMM()
    test_universe = list(TICKERS[:universe_size])
    if os.path.exists("delisted_candidates.txt"):
        with open("delisted_candidates.txt", "r") as f:
            delisted = [line.strip() for line in f if line.strip()]
            test_universe.extend(delisted[:10])
    
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        main_task = progress.add_task("[yellow]Simulating...", total=len(reb_dates))
        for i, reb_date in enumerate(reb_dates):
            progress.update(main_task, description=f"Processing {reb_date.date()}...")
            universe_metrics = []
            for symbol in test_universe:
                f = get_pit_factors(symbol, reb_date, cache=ticker_cache)
                if f:
                    f['backtest'] = True
                    score_res = calculate_institutional_score(f)
                    f['total_score'] = score_res['total_score']
                    universe_metrics.append(f)
            if not universe_metrics:
                progress.advance(main_task)
                continue
            df_snapshot = pd.DataFrame(universe_metrics)
            
            # --- Concentration Cap: 2-Quarter Consecutive Hold Constraint (v4.4) ---
            prev_picks = history[-1].get('picks', '').split(', ') if len(history) >= 1 else []
            prev_prev_picks = history[-2].get('picks', '').split(', ') if len(history) >= 2 else []
            blocked_symbols = set(prev_picks) & set(prev_prev_picks)
            
            # Filter out blocked symbols from this rebalance
            if blocked_symbols:
                df_snapshot = df_snapshot[~df_snapshot['Symbol'].isin(blocked_symbols)]
            
            # Hard filter for zero-score data failures (v9.6)
            df_snapshot = df_snapshot[df_snapshot['total_score'] > 5]
            top_picks = df_snapshot.nlargest(10, 'total_score')
            
            # 2. Performance Phase (Forward Return + Slippage)
            next_date = reb_dates[i+1] if i + 1 < len(reb_dates) else end_date
            period_returns = []
            for _, row in top_picks.iterrows():
                symbol = row.get('Symbol', 'Unknown')
                mcap = row.get('Market_Cap', 1e8) / 1e7
                if mcap > 50000: slip = 0.2
                elif mcap > 15000: slip = 0.5
                elif mcap > 5000: slip = 1.0
                else: slip = 2.0
                try:
                    price_data = yf.download(symbol, start=reb_date, end=next_date, progress=False)
                    if not price_data.empty:
                        p_start = float(price_data['Close'].iloc[0])
                        p_end = float(price_data['Close'].iloc[-1])
                        g_ret = (p_end - p_start) / p_start
                        net_ret = g_ret - (slip/100 * 2) - 0.002 
                        period_returns.append(net_ret)
                    else:
                        period_returns.append(-0.5)
                except:
                    period_returns.append(-1.0)
            avg_ret = float(np.mean(period_returns)) if period_returns else 0.0
            try:
                bnch_data = yf.download("^NSEI", start=reb_date, end=next_date, progress=False)
                bnch_ret = (float(bnch_data['Close'].iloc[-1]) - float(bnch_data['Close'].iloc[0])) / float(bnch_data['Close'].iloc[0])
            except:
                bnch_ret = 0.0
            
            # --- Regime-Aware Position Sizing (v5.0 Stress Test Support) ---
            # Simulate 1-day execution lag in Stress Mode
            regime_detect_date = reb_date - timedelta(days=1) if stress_mode else reb_date
            regime_hmm = hmm.predict_regime(target_date=regime_detect_date)
            
            # Exposure Multipliers (Normal vs. Stress)
            BEAR_EXP = 0.4 if stress_mode else 0.1
            VOL_EXP = 0.6 if stress_mode else 0.3
            
            try:
                # --- EMA Stability Filter (v4.4: 300D History) ---
                start_300d = reb_date - timedelta(days=300)
                hist_long = yf.download("^NSEI", start=start_300d, end=reb_date, progress=False)
                
                if hist_long.empty:
                    regime, exposure = "BULLISH", 1.0
                else:
                    # 1. Price vs EMA Filters (Stabilized with 300 days)
                    price_now = float(hist_long['Close'].values.flatten()[-1])
                    ema_200 = float(hist_long['Close'].ewm(span=200).mean().values.flatten()[-1])
                    ema_50 = float(hist_long['Close'].ewm(span=50).mean().values.flatten()[-1])
                    
                    # 2. Volatility Spike Detection (Trailing 20 days)
                    rets = hist_long['Close'].pct_change().dropna()
                    vol_now = float(rets.tail(20).std() * (252**0.5) * 100)
                    
                    # 3. Decision Logic
                    if price_now < ema_200 or price_now < ema_50:
                        regime, exposure = "BEARISH", BEAR_EXP
                    elif vol_now > 25.0:
                        regime, exposure = "VOLATILE", VOL_EXP
                    elif regime_hmm == "BULLISH":
                        regime, exposure = "BULLISH", 1.0
                    else:
                        regime, exposure = "VOLATILE", 0.5
            except Exception:
                regime, exposure = "VOLATILE", 0.5
            
            # Weighted Return Calculation (Cash yield assumed at 5% p.a. -> 1.25% per 3M)
            risk_free_3m = 0.0125 
            weighted_ret = (avg_ret * exposure) + (risk_free_3m * (1 - exposure))
            portfolio_value *= (1 + weighted_ret)
            
            history.append({
                "date": reb_date.date(), 
                "portfolio_value": portfolio_value, 
                "period_ret": weighted_ret * 100, 
                "raw_stock_ret": avg_ret * 100,
                "benchmark_ret": float(bnch_ret) * 100, 
                "regime": regime,
                "exposure": exposure,
                "picks": ", ".join(top_picks['Symbol'].head(3).tolist())
            })
            progress.advance(main_task)

    df_results = pd.DataFrame(history)
    if df_results.empty: return
    m = calculate_risk_metrics(df_results['period_ret'].tolist(), df_results['benchmark_ret'].tolist())
    table = Table(title="Institutional Backtest Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("CAGR", f"{m['CAGR']:.2f}%")
    table.add_row("Sharpe Ratio", f"{m['Sharpe']:.2f}")
    table.add_row("Max Drawdown", f"{m['MaxDD']:.2f}%")
    table.add_row("Calmar Ratio", f"{m['Calmar']:.2f}")
    table.add_row("Information Ratio", f"{m['IR']:.2f}")
    table.add_row("Annual Alpha", f"{m['Alpha']:+.2f}%")
    console.print(table)
    with open("qarp_backtest_report.md", "w") as f:
        f.write(f"# QARP {'STRESS TEST ' if stress_mode else 'Institutional Validation'} Report (v5.0)\n\n")
        f.write(f"- Backtest Period: {start_date.date()} to {end_date.date()}\n")
        f.write(f"- Rebalance Frequency: {rebal_freq}\n")
        f.write(f"- Mode: {'STRESS (High Risk/Aggressive)' if stress_mode else 'Normal (Institutional/Conservative)'}\n")
        f.write(f"- Regime Detection: Gaussian HMM (Bullish/Volatile/Bearish)\n")
        f.write(f"- Exposure Tuning (Normal/Stress): Bear={0.1}/{0.4}, Volatile={0.3}/{0.6}\n")
        f.write(f"- Execution Lag: {'1 Day (Simulated)' if stress_mode else 'None (Day-Of)'}\n")
        f.write(f"- Slippage Modeling: Tiered (0.2% - 2.0%)\n")
        f.write(f"- Transaction Costs: 0.2% per round-trip\n\n")
        
        f.write("## Performance Metrics\n")
        f.write(f"| Metric | Result |\n| :--- | :--- |\n")
        f.write(f"| CAGR | {m['CAGR']:.2f}% |\n")
        f.write(f"| Sharpe | {m['Sharpe']:.2f} |\n")
        f.write(f"| MaxDD | {m['MaxDD']:.2f}% |\n")
        f.write(f"| Alpha | {m['Alpha']:+.2f}% |\n")
        f.write(f"| IR | {m['IR']:.2f} |\n\n")
        
        f.write("## Equity Curve Breakdown\n")
        f.write(df_results[['date', 'regime', 'exposure', 'period_ret', 'benchmark_ret', 'picks']].to_markdown(index=False))

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--universe", type=int, default=60)
    parser.add_argument("--stress", action="store_true", help="Enable Stress Test Mode (higher BEAR exposure)")
    parser.add_argument("--rebal", type=str, default="MS", help="Rebalance frequency (e.g., MS, 3MS, W)")
    args = parser.parse_args()
    run_backtest(years=args.years, universe_size=args.universe, stress_mode=args.stress, rebal_freq=args.rebal)
