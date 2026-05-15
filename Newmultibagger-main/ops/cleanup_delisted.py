import os
import sqlite3

# Safe list to NEVER delete automatically
WHITELIST = ["TATAMOTORS.NS", "REC.NS", "RECLTD.NS", "RELIANCE.NS", "SBIN.NS", "HDFCBANK.NS"]

def cleanup():
    candidates_file = "delisted_candidates.txt"
    if not os.path.exists(candidates_file):
        print("No candidates file found.")
        return

    with open(candidates_file) as f:
        candidates = [line.strip() for line in f if line.strip()]

    to_delete = []
    for c in candidates:
        if c in WHITELIST:
            print(f"⚠️ Skipping WHITELISTED stock: {c}")
        else:
            to_delete.append(c)

    if not to_delete:
        print("No stocks to process.")
        return

    print(f"Preparing to inject synthetic terminal records for: {to_delete}")

    # 1. DB Cleanup
    db_path = "runtime/stocks.db" if os.path.exists("runtime/stocks.db") else "stocks.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for sym in to_delete:
        # Instead of deleting, mark them as delisted with -100% returns for backtesting
        cursor.execute("""
            UPDATE multibaggers 
            SET ret_1m = -100.0, 
                ret_3m = -100.0, 
                ret_6m = -100.0, 
                backtest_cagr = -100.0, 
                score = 0,
                ml_rank_score = 0,
                sector = 'DELISTED'
            WHERE symbol = ?
        """, (sym,))
        
        updated = cursor.rowcount > 0
        
        # Also ensure fundamentals_pit reflects this for the PIT backtests
        cursor.execute("""
            UPDATE fundamentals_pit 
            SET ret_1m = -100.0, 
                ret_3m = -100.0, 
                ret_6m = -100.0, 
                score = 0,
                ml_rank_score = 0,
                sector = 'DELISTED'
            WHERE symbol = ?
        """, (sym,))
        
        if updated or cursor.rowcount > 0:
            print(f"✅ Injected synthetic terminal record (-100%) for {sym} in DB.")
        else:
            print(f"⚠️ {sym} not found in DB.")

    conn.commit()
    conn.close()

    # 2. Update ticker_list.py
    ticker_file = "ticker_list.py"
    if os.path.exists(ticker_file):
        with open(ticker_file) as f:
            lines = f.readlines()

        new_lines = []
        removed_count = 0
        for line in lines:
            for sym in to_delete:
                if f'"{sym}"' in line or f"'{sym}'" in line:
                    if sym in line:
                        line = line.replace(f'"{sym}",', "")
                        line = line.replace(f"'{sym}',", "")
                        line = line.replace(f'"{sym}"', "")
                        line = line.replace(f"'{sym}'", "")
                        print(f"removed {sym} from {ticker_file}")
                        removed_count += 1

            if line.strip() != "" and line.strip() != ",":
                new_lines.append(line)

        with open(ticker_file, "w") as f:
            f.writelines(new_lines)

        print(f"Updated {ticker_file} (removed references).")


if __name__ == "__main__":
    cleanup()
