# QARP Institutional Validation Report (v4.4 - Regime-Aware)

- Backtest Period: 2025-04-03 to 2026-04-03
- Regime Detection: Gaussian HMM (Bullish/Volatile/Bearish)
- Position Sizing: Dynamic Exposure (Bull=100%, Vol=50%, Bear=10%)
- Slippage Modeling: Tiered (0.2% - 2.0%)
- Transaction Costs: 0.2% per round-trip

## Performance Metrics
| Metric | Result |
| :--- | :--- |
| CAGR | 7.11% |
| Sharpe | 1.71 |
| MaxDD | -1.03% |
| Alpha | +13.10% |
| IR | 1.43 |

## Equity Curve Breakdown
| date       | regime   |   exposure |   period_ret |   benchmark_ret | picks               |
|:-----------|:---------|-----------:|-------------:|----------------:|:--------------------|
| 2025-05-01 | BULLISH  |        1   |      1.49188 |         0.89807 | IRFC.NS             |
| 2025-08-01 | BEARISH  |        0.1 |      1.71603 |         4.70887 | POLYCAB.NS, IRFC.NS |
| 2025-11-01 | BULLISH  |        1   |      4.83255 |        -1.71833 | TCS.NS              |
| 2026-02-01 | BEARISH  |        0.1 |     -1.03115 |        -9.46773 | IRFC.NS, TCS.NS     |