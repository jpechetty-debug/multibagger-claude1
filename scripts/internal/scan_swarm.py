"""
Sovereign Engine: Swarm Intelligence Validation Scan
Uses the MiroFish Multi-Agent Engine to predict the trajectory of high-conviction picks.
"""

import sys
import os
import argparse
import logging
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("scan_swarm")

from modules.mirofish_client import MiroFishClient
from modules.news_sentiment import engine as news_engine

import sqlite3
import os

def get_real_context(ticker: str) -> str:
    """Fetch fundamental and technical context from the database for the swarm debate."""
    db_path = "stocks.db"
    
    # v11.0: Fetch real-time news sentiment context
    sentiment_data = news_engine.get_alpha_signal(ticker)
    news_snippet = "\n".join([f"- {h}" for h in sentiment_data.get("headlines", [])])
    sentiment_context = f"""
        # News & Sentiment Context (v11.0)
        - **Sentiment Score**: {sentiment_data['sentiment_score']} ({sentiment_data['alignment']})
        - **Recent Headlines**:
        {news_snippet if news_snippet else 'No recent news found.'}
    """

    if not os.path.exists(db_path):
        return f"Context for {ticker}: No database found. {sentiment_context}"
        
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Fetch latest metrics from multibaggers table
        cursor.execute("SELECT * FROM multibaggers WHERE symbol = ?", (ticker,))
        row = cursor.fetchone()
        
        if not row:
            return f"Context for {ticker}: Ticker not found in institutional database. {sentiment_context}"
            
        context = f"""
        # Institutional Context for {ticker}
        - **Sector**: {row['sector']}
        - **Sovereign Score**: {row['score']}/100
        - **Valuation**: PE Ratio of {row['pe_ratio'] if row['pe_ratio'] else 'N/A'}, PEG Ratio of {row['peg_ratio'] if row['peg_ratio'] else 'N/A'}
        - **Profitability**: ROE of {row['roe']}% , CFO/PAT Ratio of {row['cfo_pat_ratio'] if row['cfo_pat_ratio'] else 'N/A'}
        - **Growth**: Sales Growth (TTM) of {row['sales_growth']}% , 5Y Sales CAGR of {row['sales_cagr_5y']}%
        - **Momentum**: 52W High distance: {row['down_from_52w']}% , RSI: {row['rsi']}
        - **Risk**: Debt/Equity of {row['debt_equity']}
        - **Thesis Summary**: {row['rating']} rating with a current conviction boost of {row['conviction_boost']}.
        
        {sentiment_context}
        """
        conn.close()
        return context
    except Exception as e:
        logger.warning(f"Failed to fetch real context for {ticker}: {e}")
        return f"Heuristic context for {ticker}: Fundamental data extraction error."

def run_swarm_scan(tickers: list):
    console = Console()
    console.print(Panel(f"[bold magenta]MiroFish Swarm Validation[/bold magenta]\nLaunching multi-agent simulation for: {', '.join(tickers)}", border_style="magenta"))
    
    client = MiroFishClient()
    
    table = Table(title="Swarm Consensus Output")
    table.add_column("Ticker", style="cyan", no_wrap=True)
    table.add_column("MiroFish Swarm Report", style="green")
    
    for ticker in tickers:
        console.print(f"\n[blue]Generating real-time context for {ticker}...[/blue]")
        context = get_real_context(ticker)
        
        console.print(f"[blue]Submitting to MiroFish Simulation Engine...[/blue]")
        # This will either connect to MiroFish on :5001 or fallback
        report = client.simulate_ticker(ticker, context)
        
        # PERSISTENCE: Save to data/swarm_reports/ for API consumption
        try:
            os.makedirs("data/swarm_reports", exist_ok=True)
            report_path = os.path.join("data", "swarm_reports", f"{ticker}.md")
            with open(report_path, "w") as f:
                f.write(report)
            console.print(f"[green]Report saved to {report_path}[/green]")
        except Exception as e:
            logger.error(f"Failed to save report for {ticker}: {e}")
            
        table.add_row(ticker, report[:200] + "..." if len(report) > 200 else report)
        
    console.print("\n", table)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MiroFish Swarm simulation on target tickers.")
    parser.add_argument("--tickers", type=str, required=True, help="Comma-separated list of tickers")
    parser.add_argument("--deep", action="store_true", help="Run high-fidelity deep simulation")
    parser.add_argument("--push", action="store_true", help="Push conviction updates to database")
    
    args = parser.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    
    if not tickers:
        logger.error("No valid tickers provided.")
        sys.exit(1)
        
    run_swarm_scan(tickers)
