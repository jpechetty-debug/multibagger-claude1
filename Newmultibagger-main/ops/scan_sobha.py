import modules.adapters.yf_patch  # noqa: F401
import screener

if __name__ == "__main__":
    screener.TICKERS = ["SOBHA.NS"]
    screener.main()
