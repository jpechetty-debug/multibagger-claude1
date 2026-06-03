# QARP Institutional Validation Report (v5.0) [DATA LIMITED — NOT REPRESENTATIVE]



> [!WARNING]

> **BACKTEST DATA LIMITATION**: yfinance free API limits historical quarterly statement downloads to the most recent 4-5 quarters.

> Rebalance periods prior to this window were skipped during simulation because dynamic fundamental metrics (like Piotroski F-Score) could not be calculated without look-ahead bias.

> Therefore, the backtest results below only reflect the most recent ~1 year of history, NOT the full stated period, and should not be used as representative of long-term performance.



- Backtest Period: 2023-06-04 to 2026-06-03

- Rebalance Frequency: 3MS

- Mode: Normal (Institutional/Conservative)

- Regime Detection: Gaussian HMM (Bullish/Volatile/Bearish)

- Exposure Tuning (Normal/Stress): Bear=0.1/0.4, Volatile=0.3/0.6

- Execution Lag: None (Day-Of)

- Slippage Modeling: Tiered (0.2% - 2.0%)

- Transaction Costs: 0.2% per round-trip



## Performance Metrics

| Metric | Result |

| :--- | :--- |

| CAGR | -9.98% |

| Sharpe | -0.42 |

| MaxDD | -25.17% |

| Alpha | -10.19% |

| IR | -0.62 |



## Equity Curve Breakdown

| date       | regime   |   exposure |   portfolio_value |   period_ret |   benchmark_ret | picks      |

|:-----------|:---------|-----------:|------------------:|-------------:|----------------:|:-----------|

| 2025-04-01 | BEARISH  |        0.1 |          101.125  |      1.125   |        10.257   |            |

| 2025-07-01 | BULLISH  |        1   |          109.229  |      8.01407 |        -2.76214 | POLYCAB.NS |

| 2025-10-01 | BEARISH  |        0.1 |          111.663  |      2.22816 |         5.27554 | TCS.NS     |

| 2026-01-01 | BULLISH  |        1   |           83.5566 |    -25.1708  |       -13.2605  | TCS.NS     |

| 2026-04-01 | BEARISH  |        0.1 |           87.6871 |      4.94331 |         2.41916 | POLYCAB.NS |



*Note: yfinance free API limits historical quarterly statement downloads to the most recent 4-5 quarters. Rebalance periods prior to this window were skipped during the backtest because fundamental metrics (like Piotroski F-Score) could not be calculated dynamically without look-ahead bias.*