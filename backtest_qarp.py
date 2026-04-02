# backtest_qarp.py
"""
Sovereign AI Trading Engine - QARP 8-Factor Walk-Forward Backtester (v4.0)
Validates the QARP thesis against historical PIT (Point-In-Time) data.
"""

import os
import sys
import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn

# Ensure project modules are importable
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ticker_list import TICKERS
from db.repository import get_connection

console = Console()

def print_header(text):
    console.print(f"\n[bold cyan]{'='*80}[/bold cyan]")
    console.print(f" [bold white]{text}[/bold white]")
    console.print(f"[bold cyan]{'='*80}[/bold cyan]\n")

# ── PIT Factor Extraction ─────────────────────────────────────────────────────

def get_pit_factors(symbol, target_date):
    """
    Fetch fundamentals for 'symbol' that would have been known on 'target_date'.
    Simulates reporting lag (approx 3 months post quarter end).
    """
    try:
        ticker = yf.Ticker(symbol)
        income = ticker.quarterly_income_stmt
        balance = ticker.quarterly_balance_sheet
        cashflow = ticker.quarterly_cashflow
        
        if income.empty or balance.empty:
            return None
            
        # Reporting lag: usually data is published 1-2 months after quarter end.
        # We assume 3 months to be extra conservative (no look-ahead).
        reporting_lag = pd.Timedelta(days=90)
        
        # Available quarters
        dates = pd.to_datetime(income.columns)
        available_quarters = [d for d in dates if (d + reporting_lag) <= pd.to_datetime(target_date)]
        
        if not available_quarters:
            return None
            
        latest_q = available_quarters[0] # yf returns newest first
        
        # Extract metrics
        rev = income[latest_q].get('Total Revenue', 0)
        prev_q = dates[1] if len(dates) > 1 else None
        rev_prev = income[prev_q].get('Total Revenue', 0) if prev_q else 0
        sales_growth = (rev - rev_prev) / rev_prev if rev_prev > 0 else 0
        
        net_income = income[latest_q].get('Net Income', 0)
        equity = balance[latest_q].get('Stockholders Equity', 1e6)
        roe = net_income / equity if equity > 0 else 0
        
        total_debt = balance[latest_q].get('Total Debt', 0)
        debt_equity = total_debt / equity if equity > 0 else 0
        
        cfo = cashflow[latest_q].get('Operating Cash Flow', 0)
        cfo_pat = cfo / net_income if net_income > 0 else 0
        
        # Simple Piotroski F-Score component (stub)
        f_score = 5 # default moderate
        if net_income > 0: f_score += 1
        if cfo > 0: f_score += 1
        if cfo > net_income: f_score += 1
        
        factors = {
            "symbol": symbol,
            "sales_growth": sales_growth,
            "roe": roe,
            "debt_equity": debt_equity,
            "cfo_pat": cfo_pat,
            "f_score": f_score,
            "market_cap": ticker.info.get('marketCap', 1e8)
        }
        return factors
    except Exception:
        return None

# ── Scoring Engine ────────────────────────────────────────────────────────────

def calculate_qarp_score(factors):
    """Simplified 8-factor scoring for backtest."""
    score = 0
    # Growth (30%)
    score += min(max(factors['sales_growth'] * 100, 0), 30) 
    # Quality (30%)
    score += min(max(factors['roe'] * 100, 0), 20)
    score += 10 if factors['debt_equity'] < 0.5 else 0
    # Efficiency (20%)
    score += 10 if factors['cfo_pat'] > 1.0 else 0
    score += factors['f_score'] * 2
    # Value (20%)
    # PE/PEG would need historical pricing at PIT date. 
    # For now, we use MCAP as a size filter factor.
    score += 10 if factors['market_cap'] < 50000 * 1e7 else 0 # Small/Mid cap nudge
    return score

# ── Simulation Loop ───────────────────────────────────────────────────────────

def run_backtest(years=2, rebalance="quarterly", universe_size=50):
    print_header(f"Strategy: QARP Walk-Forward ({years}Y)")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365 * years)
    
    # Rebalance dates
    if rebalance == "quarterly":
        reb_dates = pd.date_range(start=start_date, end=end_date, freq='3MS')
    else:
        reb_dates = pd.date_range(start=start_date, end=end_date, freq='MS')
        
    portfolio_value = 100.0
    history = []
    
    # Selection Universe
    test_universe = TICKERS[:universe_size]
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        
        main_task = progress.add_task("[yellow]Simulating Portfolio...", total=len(reb_dates))
        
        for i, reb_date in enumerate(reb_dates):
            progress.update(main_task, description=f"[yellow]Processing {reb_date.date()}...")
            
            # 1. Selection Phase
            universe_metrics = []
            for symbol in test_universe:
                f = get_pit_factors(symbol, reb_date)
                if f:
                    f['qarp_score'] = calculate_qarp_score(f)
                    universe_metrics.append(f)
            
            if not universe_metrics:
                progress.advance(main_task)
                continue
                
            df_snapshot = pd.DataFrame(universe_metrics)
            top_picks = df_snapshot.nlargest(10, 'qarp_score')['symbol'].tolist()
            
            # 2. Performance Phase (Forward Return)
            next_date = reb_dates[i+1] if i+1 < len(reb_dates) else end_date
            
            period_returns = []
            for symbol in top_picks:
                try:
                    price_data = yf.download(symbol, start=reb_date, end=next_date, progress=False)
                    if not price_data.empty:
                        # Ensure we get a single value from the Series
                        p_start = float(price_data['Close'].iloc[0])
                        p_end = float(price_data['Close'].iloc[-1])
                        ret = (p_end - p_start) / p_start if p_start > 0 else 0
                        period_returns.append(ret)
                except Exception as e:
                    # console.print(f"Error for {symbol}: {e}")
                    pass
            
            avg_ret = float(np.mean(period_returns)) if period_returns else 0.0
            
            # Benchmark Return (^NSEI)
            try:
                bnch_data = yf.download("^NSEI", start=reb_date, end=next_date, progress=False)
                if not bnch_data.empty:
                    b_start = float(bnch_data['Close'].iloc[0])
                    b_end = float(bnch_data['Close'].iloc[-1])
                    bnch_ret = (b_end - b_start) / b_start if b_start > 0 else 0.0
                else:
                    bnch_ret = 0.0
            except:
                bnch_ret = 0.0
                
            portfolio_value *= (1 + avg_ret)
            
            history.append({
                "date": reb_date.date(),
                "portfolio_value": portfolio_value,
                "period_ret": avg_ret * 100,
                "benchmark_ret": float(bnch_ret) * 100,
                "picks": ", ".join(top_picks[:3]) + "..."
            })
            
            progress.advance(main_task)

    # ── Report Generation ─────────────────────────────────────────────────────
    
    df_results = pd.DataFrame(history)
    if df_results.empty:
        console.print("[red]Backtest failed: No data recovered.[/red]")
        return

    # Metrics
    total_ret = (df_results['portfolio_value'].iloc[-1] - 100) / 100
    cagr = ((1 + total_ret) ** (1/years)) - 1
    
    # Benchmarking
    bnch_hist = yf.download("^NSEI", start=start_date, end=end_date, progress=False)
    if not bnch_hist.empty:
        b_total_start = float(bnch_hist['Close'].iloc[0])
        b_total_end = float(bnch_hist['Close'].iloc[-1])
        bnch_total_ret = (b_total_end - b_total_start) / b_total_start if b_total_start > 0 else 0.0
    else:
        bnch_total_ret = 0.0
    bnch_cagr = ((1 + bnch_total_ret) ** (1/years)) - 1 if bnch_total_ret > -1 else 0
    
    alpha = cagr - bnch_cagr
    
    table = Table(title="QARP Walk-Forward Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Sovereign QARP", style="green")
    table.add_column("Nifty 50", style="magenta")
    
    table.add_row("Total Return", f"{total_ret*100:.2f}%", f"{bnch_total_ret*100:.2f}%")
    table.add_row("CAGR", f"{cagr*100:.2f}%", f"{bnch_cagr*100:.2f}%")
    table.add_row("Annual Alpha", f"{alpha*100:+.2f}%", "-")
    
    console.print(table)
    
    # Save Report
    with open("qarp_backtest_report.md", "w") as f:
        f.write("# QARP Analytical Backtest Report\n")
        f.write(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Executive Summary\n")
        f.write(f"- **Strategy**: QARP (Quality at Reasonable Price) 8-Factor\n")
        f.write(f"- **Lookback**: {years} Years\n")
        f.write(f"- **Selection Universe**: Top {universe_size} Multi-cap picks\n")
        f.write(f"- **Rebalancing**: {rebalance.capitalize()}\n\n")
        f.write(f"### Performance Comparison\n")
        f.write(f"| Metric | Sovereign QARP | Nifty 50 |\n")
        f.write(f"| :--- | :--- | :--- |\n")
        f.write(f"| Total Return | {total_ret*100:.2f}% | {bnch_total_ret*100:.2f}% |\n")
        f.write(f"| CAGR | {cagr*100:.2f}% | {bnch_cagr*100:.2f}% |\n")
        f.write(f"| Alpha | **{alpha*100:+.2f}%** | - |\n\n")
        f.write(f"### Rebalancing History\n")
        f.write(df_results[['date', 'period_ret', 'benchmark_ret', 'picks']].to_markdown(index=False))

    console.print(f"\n[bold green]✅ Report saved to qarp_backtest_report.md[/bold green]")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=1) # Default 1 to be fast for demo
    parser.add_argument("--rebalance", default="quarterly")
    parser.add_argument("--universe", default="top-50")
    args = parser.parse_args()
    
    size = 50 if args.universe == "top-50" else (100 if args.universe == "top-100" else 500)
    
    run_backtest(years=args.years, rebalance=args.rebalance, universe_size=size)
