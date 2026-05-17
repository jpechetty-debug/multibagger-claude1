import pandas as pd
import numpy as np
import yfinance as yf

def fetch_forward_prices(df_input, months=3):
    """Fetch forward prices using yfinance monthly data."""
    df = df_input.copy()
    symbols = df["symbol"].unique().tolist()
    print(f"Fetching monthly history for {len(symbols)} symbols...")

    hist_dfs = []
    chunk_size = 200
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i+chunk_size]
        try:
            h = yf.download(chunk, period="10y", interval="1mo", progress=False)
            if not h.empty:
                if isinstance(h.columns, pd.MultiIndex):
                    if "Close" in h.columns:
                        hist_dfs.append(h["Close"])
                else:
                    if "Close" in h:
                        hist_dfs.append(pd.DataFrame({chunk[0]: h["Close"]}))
        except Exception as e:
            print(f"Error fetching chunk: {e}")

    if not hist_dfs:
        return pd.Series(dtype=float)

    # Join chunks avoiding duplicate columns
    close_prices = pd.concat(hist_dfs, axis=1)
    close_prices = close_prices.loc[:,~close_prices.columns.duplicated()]

    if close_prices.index.tz is not None:
        close_prices.index = close_prices.index.tz_convert(None)

    df["as_of_date"] = pd.to_datetime(df["as_of_date"])
    df["target_date"] = df["as_of_date"] + pd.DateOffset(months=months)

    def get_forward_price(row):
        sym = row["symbol"]
        t_date = row["target_date"]
        if sym not in close_prices.columns:
            return np.nan

        sym_prices = close_prices[sym].dropna()
        if sym_prices.empty:
            return np.nan

        # Find closest date >= target_date
        future_prices = sym_prices[sym_prices.index >= t_date]
        if future_prices.empty:
            return np.nan

        closest_date = future_prices.index[0]
        if (closest_date - t_date).days <= 35:
            return future_prices.iloc[0]
        return np.nan

    return df.apply(get_forward_price, axis=1)
