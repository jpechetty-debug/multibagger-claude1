import screener

import modules.adapters.yf_patch  # noqa: F401

if __name__ == "__main__":
    screener.TICKERS = ["SOBHA.NS"]
    screener.main()
