# QARP STRESS TEST  Report (v5.0)

- Backtest Period: 2021-04-06 to 2026-04-05
- Rebalance Frequency: MS
- Mode: STRESS (High Risk/Aggressive)
- Regime Detection: Gaussian HMM (Bullish/Volatile/Bearish)
- Exposure Tuning (Normal/Stress): Bear=0.1/0.4, Volatile=0.3/0.6
- Execution Lag: 1 Day (Simulated)
- Slippage Modeling: Tiered (0.2% - 2.0%)
- Transaction Costs: 0.2% per round-trip

## Performance Metrics
| Metric | Result |
| :--- | :--- |
| CAGR | -0.23% |
| Sharpe | -0.03 |
| MaxDD | -6.72% |
| Alpha | +0.35% |
| IR | 0.04 |

## Equity Curve Breakdown
| date       | regime   |   exposure |   period_ret |   benchmark_ret | picks                       |
|:-----------|:---------|-----------:|-------------:|----------------:|:----------------------------|
| 2025-01-01 | BEARISH  |        0.4 |   -2.90056   |       -1.09822  | IRFC.NS, TCS.NS, POLYCAB.NS |
| 2025-02-01 | BEARISH  |        0.4 |   -6.72282   |       -5.78078  | IRFC.NS, TCS.NS, POLYCAB.NS |
| 2025-03-01 | BEARISH  |        0.4 |    0.75      |        4.7307   |                             |
| 2025-04-01 | BEARISH  |        0.4 |    0.538945  |        5.0441   | IRFC.NS                     |
| 2025-05-01 | BULLISH  |        1   |   11.195     |        1.65936  | IRFC.NS                     |
| 2025-06-01 | VOLATILE |        0.5 |    0.625     |        3.33865  |                             |
| 2025-07-01 | VOLATILE |        0.5 |   -2.12872   |       -3.82295  | POLYCAB.NS, IRFC.NS         |
| 2025-08-01 | BEARISH  |        0.4 |    0.842367  |        0.24303  | POLYCAB.NS, IRFC.NS         |
| 2025-09-01 | BEARISH  |        0.4 |    0.75      |        0.857866 |                             |
| 2025-10-01 | BEARISH  |        0.4 |    1.38617   |        3.56655  | IRFC.NS, TCS.NS             |
| 2025-11-01 | VOLATILE |        0.5 |    0.0707019 |        1.60073  | IRFC.NS, TCS.NS             |
| 2025-12-01 | VOLATILE |        0.5 |    0.625     |       -0.111551 |                             |
| 2026-01-01 | VOLATILE |        0.5 |   -1.16768   |       -3.15874  | IRFC.NS, TCS.NS             |
| 2026-02-01 | BEARISH  |        0.4 |   -4.82849   |        0.359728 | IRFC.NS, TCS.NS             |
| 2026-03-01 | BEARISH  |        0.4 |    0.75      |       -8.79243  |                             |
| 2026-04-01 | BEARISH  |        0.4 |    0.341647  |        0.14859  | IRFC.NS, POLYCAB.NS         |