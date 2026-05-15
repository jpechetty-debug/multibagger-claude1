import sqlite3
import pandas as pd
import yfinance as yf

conn = sqlite3.connect('runtime/stocks.db')
query = \"\"\"
    SELECT symbol, as_of_date, price as pit_price
    FROM fundamentals_pit
    WHERE sector != 'DELISTED'
    LIMIT 10
\"\"\"
df = pd.read_sql(query, conn)
conn.close()

symbols = df['symbol'].unique().tolist()
hist = yf.download(symbols, period='5y', interval='1mo', progress=False)

if isinstance(hist.columns, pd.MultiIndex):
    close_prices = hist['Close']
else:
    close_prices = pd.DataFrame({symbols[0]: hist['Close']})

print(close_prices.head())
