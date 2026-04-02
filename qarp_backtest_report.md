# QARP Institutional Validation Report (v4.4 - Regime-Aware)

- Backtest Period: 2024-04-02 to 2026-04-02
- Regime Detection: Gaussian HMM (Bullish/Volatile/Bearish)
- Position Sizing: Dynamic Exposure (Bull=100%, Vol=50%, Bear=10%)
- Slippage Modeling: Tiered (0.2% - 2.0%)
- Transaction Costs: 0.2% per round-trip

## Performance Metrics
| Metric | Result |
| :--- | :--- |
| CAGR | 3.15% |
| Sharpe | 1.28 |
| MaxDD | -1.02% |
| Alpha | +5.10% |
| IR | 0.61 |

## Equity Curve Breakdown
| date       | regime   |   exposure |   period_ret |   benchmark_ret | picks                       |
|:-----------|:---------|-----------:|-------------:|----------------:|:----------------------------|
| 2025-02-01 | BEARISH  |        0.1 |  -0.00462034 |         3.6285  | IRFC.NS, TCS.NS, POLYCAB.NS |
| 2025-05-01 | BULLISH  |        1   |   1.49188    |         0.89807 | IRFC.NS                     |
| 2025-08-01 | BEARISH  |        0.1 |   2.56694    |         4.70887 | POLYCAB.NS                  |
| 2025-11-01 | BULLISH  |        1   |   0.897751   |        -1.71833 | IRFC.NS, TCS.NS             |
| 2026-02-01 | BEARISH  |        0.1 |  -1.02127    |        -9.31745 | IRFC.NS, TCS.NS             |