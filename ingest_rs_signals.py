import pandas as pd
import sys
import os

# Import repository layer
sys.path.append(os.getcwd())
from db.repository import save_multibaggers

def ingest():
    csv_path = "tmp_rs_data.csv"
    if not os.path.exists(csv_path):
        print(f"Error: {csv_path} not found.")
        return

    # Read CSV
    # Columns: #,Symbol,Company Name,Sector,Price (₹),RS% (Feb3→Apr2),DoD%,Signal
    df = pd.read_csv(csv_path, skiprows=3) # Skip the headers/banner rows
    # The read_csv with skiprows might need adjustment if the headers are on a specific line.
    # Looking at the view_file output, row 4 is the header row.
    df = pd.read_csv(csv_path)
    
    # Clean up the dataframe (find the row where Symbol exists)
    header_idx = df[df.apply(lambda r: 'Symbol' in r.values, axis=1)].index[0]
    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx+1:].reset_index(drop=True)
    
    # Filter out empty or non-symbol rows
    df = df[df['Symbol'].notna() & (df['Symbol'] != '#')]
    
    # Ticker suffixing
    df['Symbol'] = df['Symbol'].astype(str).str.strip().apply(lambda x: f"{x}.NS" if not x.endswith(".NS") else x)
    
    # Mapping
    # Price cleaning
    df['Price (₹)'] = pd.to_numeric(df['Price (₹)'], errors='coerce')
    
    # Signal to Score mapping
    def map_score(sig):
        sig = str(sig).upper()
        if 'STRONG BUY' in sig: return 88.0
        if 'BUY' in sig: return 75.0
        if 'WATCH' in sig: return 55.0
        if 'AVOID' in sig: return 15.0
        return 50.0

    df['Score'] = df['Signal'].apply(map_score)
    df['Rating'] = df['Signal']
    
    # RS Rating (map the percentage to a 1-100 relative value if possible, or just store float)
    df['RS_Rating'] = pd.to_numeric(df['RS% (Feb3→Apr2)'], errors='coerce') * 100
    
    # Prepare for save_multibaggers
    # Expected columns: Symbol, Price, Sector, Score, Rating, Name, etc.
    df_save = df.rename(columns={
        "Company Name": "Name",
        "Price (₹)": "Price",
        "Sector": "Sector",
        "Signal": "Technical_Signal"
    })
    
    # Ensure mandatory columns exist for save_multibaggers
    # Symbol is already there. Price, Sector, Score, Rating as well.
    # We also need Name (it's in the mapping above)
    
    print(f"Ingesting {len(df_save)} signals into database...")
    save_multibaggers(df_save)
    print("Ingestion complete.")

if __name__ == "__main__":
    ingest()
