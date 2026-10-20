# Fabio Valentini model: mechanical CFD backtest

Source: transcript supplied in this folder. Rules were fixed in [RULES.md](RULES.md) before returns were computed; implementation is [research.py](research.py). All results are price-quote proxies for a discretionary futures order-flow model.

## Data and method

- Trades use Exness bid/ask, or HistData bid plus time-of-day median Exness spread before 2019-08-05 for US indices. Profiles use minute mid-close TPO, not exchange volume. The proxy trigger combines quote-tick bursts and up/down quote changes. HistData lacks these fields.
- Entries are at the next minute open, stop wins intrabar ties, no overnight trades. Numbers include quoted spread but exclude commission, financing and extra slippage. One candidate per model/day. Stop distance defines R. A 1R win is not necessarily a 1R POC win.
- Training and all parameter choices: 2016-10-01 through 2021-12-31, NASDAQ only. Untouched judgement interval: 2022-01-01 through 2026-09-30. The overlapping long/recent windows below are descriptive, not independent tests.
- Coverage: USTECm 2016-10-02–2026-09-29 (3,403,265 bars); US500m 2016-10-02–2026-09-30 (3,182,799 bars); DE30m 2019-08-05–2026-09-30 (2,333,047 bars); XAUUSDm 2019-01-02–2026-09-30 (2,732,845 bars). DAX and gold therefore cannot supply a full ten years.

## NASDAQ training selection

| Model | Rule | Trades | Avg R | t | Win % |
|---|---|---:|---:|---:|---:|
| trend | base | 590 | -0.407 | -8.58 | 21.4 |
| trend | proxy | 3 | -0.085 | -0.09 | 33.3 |
| trend | first90 | 375 | -0.402 | -6.40 | 21.3 |
| trend | wide_va | 273 | -0.260 | -3.49 | 26.0 |
| trend | one_r | 590 | -0.440 | -12.10 | 28.0 |
| trend | hold60 | 590 | -0.403 | -7.79 | 18.8 |
| reversion | base | 146 | -0.636 | -7.75 | 12.3 |
| reversion | proxy | 1 | -1.000 | — | 0.0 |
| reversion | first90 | 65 | -0.428 | -2.64 | 20.0 |
| reversion | wide_va | 94 | -0.617 | -5.30 | 10.6 |
| reversion | one_r | 146 | -0.660 | -10.82 | 17.1 |
| reversion | hold60 | 146 | -0.601 | -6.34 | 11.0 |

Prespecified selection rule chose **trend / wide_va**

## Out-of-sample judgement, 2022-01-01 to 2026-09-30

| Market | Model | Rule | Trades | Avg R | t | Win % | Adjusted p |
|---|---|---|---:|---:|---:|---:|---:|
| USTECm | trend | base | 554 | -0.234 | -4.17 | 22.4 | 0.000 |
| USTECm | trend | proxy | 4 | 0.017 | 0.02 | 50.0 | — |
| USTECm | trend | first90 | 382 | -0.247 | -3.95 | 22.5 | 0.001 |
| USTECm | trend | wide_va | 322 | -0.282 | -4.07 | 21.1 | 0.001 |
| USTECm | trend | one_r | 554 | -0.257 | -6.29 | 37.0 | 0.000 |
| USTECm | trend | hold60 | 554 | -0.244 | -4.21 | 20.6 | 0.000 |
| USTECm | reversion | base | 182 | -0.458 | -5.35 | 13.7 | 0.000 |
| USTECm | reversion | proxy | 5 | -1.003 | -293.50 | 0.0 | — |
| USTECm | reversion | first90 | 96 | -0.596 | -7.25 | 11.5 | 0.000 |
| USTECm | reversion | wide_va | 126 | -0.471 | -4.48 | 11.9 | 0.000 |
| USTECm | reversion | one_r | 182 | -0.471 | -7.20 | 26.4 | 0.000 |
| USTECm | reversion | hold60 | 182 | -0.474 | -5.18 | 12.1 | 0.000 |
| US500m | trend | base | 550 | -0.302 | -6.05 | 23.8 | 0.000 |
| US500m | trend | proxy | 10 | -0.309 | -1.26 | 40.0 | — |
| US500m | trend | first90 | 355 | -0.255 | -3.98 | 26.5 | 0.001 |
| US500m | trend | wide_va | 226 | -0.268 | -3.26 | 23.5 | 0.016 |
| US500m | trend | one_r | 550 | -0.300 | -7.44 | 35.1 | 0.000 |
| US500m | trend | hold60 | 550 | -0.286 | -4.94 | 21.3 | 0.000 |
| US500m | reversion | base | 128 | -0.477 | -5.00 | 14.8 | 0.000 |
| US500m | reversion | proxy | 3 | -1.000 | — | 0.0 | — |
| US500m | reversion | first90 | 54 | -0.200 | -1.09 | 24.1 | 1.000 |
| US500m | reversion | wide_va | 72 | -0.383 | -2.53 | 16.7 | 0.165 |
| US500m | reversion | one_r | 128 | -0.435 | -5.51 | 28.1 | 0.000 |
| US500m | reversion | hold60 | 128 | -0.479 | -4.94 | 12.5 | 0.000 |
| DE30m | trend | base | 519 | -0.361 | -6.77 | 20.4 | 0.000 |
| DE30m | trend | proxy | 9 | -0.059 | -0.20 | 44.4 | — |
| DE30m | trend | first90 | 349 | -0.312 | -4.37 | 20.6 | 0.000 |
| DE30m | trend | wide_va | 117 | -0.292 | -2.76 | 23.9 | 0.082 |
| DE30m | trend | one_r | 519 | -0.384 | -9.60 | 30.6 | 0.000 |
| DE30m | trend | hold60 | 519 | -0.326 | -5.24 | 17.3 | 0.000 |
| DE30m | reversion | base | 270 | -0.368 | -5.32 | 24.4 | 0.000 |
| DE30m | reversion | proxy | 3 | -1.000 | — | 0.0 | — |
| DE30m | reversion | first90 | 193 | -0.335 | -4.34 | 27.5 | 0.000 |
| DE30m | reversion | wide_va | 66 | -0.099 | -0.57 | 30.3 | 1.000 |
| DE30m | reversion | one_r | 270 | -0.404 | -7.32 | 29.6 | 0.000 |
| DE30m | reversion | hold60 | 270 | -0.389 | -5.53 | 22.2 | 0.000 |
| XAUUSDm | trend | base | 536 | -0.114 | -1.78 | 21.5 | 0.917 |
| XAUUSDm | trend | proxy | 1 | -1.000 | — | 0.0 | — |
| XAUUSDm | trend | first90 | 373 | -0.007 | -0.08 | 23.3 | 1.000 |
| XAUUSDm | trend | wide_va | 113 | -0.140 | -0.97 | 21.2 | 1.000 |
| XAUUSDm | trend | one_r | 536 | -0.080 | -1.86 | 45.9 | 0.769 |
| XAUUSDm | trend | hold60 | 536 | -0.091 | -1.27 | 20.0 | 1.000 |
| XAUUSDm | reversion | base | 184 | -0.387 | -4.44 | 14.1 | 0.000 |
| XAUUSDm | reversion | proxy | 5 | -0.198 | -0.40 | 40.0 | — |
| XAUUSDm | reversion | first90 | 89 | -0.227 | -1.84 | 20.2 | 0.830 |
| XAUUSDm | reversion | wide_va | 51 | -0.524 | -3.88 | 9.8 | 0.004 |
| XAUUSDm | reversion | one_r | 184 | -0.282 | -3.99 | 35.9 | 0.001 |
| XAUUSDm | reversion | hold60 | 184 | -0.415 | -4.62 | 9.8 | 0.000 |

Bonferroni adjusts twelve disclosed model/rule variants **within each market**. P values are omitted below 30 trades; any shown t statistic for a tiny proxy sample is descriptive only. The selected result is still one out-of-sample assessment, and daily clustering makes the naive t statistics optimistic.

## Requested account and trade windows

Each row gives trades, mean R, t, win rate, EUR 1,000 final balance and peak-to-trough drawdown at 0.5% and 2% fractional risk. A blank sample retains EUR 1,000.

### 2016-10 to 2026-09

| Market | Model | Rule | N | Avg R | t | Win % | 0.5% € | DD % | 2% € | DD % |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| USTECm | trend | base | 1144 | -0.323 | -8.82 | 21.9 | 153.91 | 86.0 | 0.43 | 100.0 |
| USTECm | trend | proxy | 7 | -0.027 | -0.05 | 42.9 | 998.92 | 1.5 | 994.06 | 5.8 |
| USTECm | trend | first90 | 757 | -0.324 | -7.30 | 21.9 | 289.43 | 73.0 | 5.89 | 99.5 |
| USTECm | trend | wide_va | 595 | -0.272 | -5.37 | 23.4 | 439.97 | 56.2 | 32.64 | 96.8 |
| USTECm | trend | one_r | 1144 | -0.352 | -12.83 | 32.3 | 131.93 | 87.3 | 0.26 | 100.0 |
| USTECm | trend | hold60 | 1144 | -0.326 | -8.41 | 19.7 | 150.79 | 86.1 | 0.38 | 100.0 |
| USTECm | reversion | base | 328 | -0.538 | -8.95 | 13.1 | 411.64 | 58.8 | 26.76 | 97.3 |
| USTECm | reversion | proxy | 6 | -1.003 | -352.00 | 0.0 | 970.29 | 3.0 | 885.53 | 11.4 |
| USTECm | reversion | first90 | 161 | -0.528 | -6.47 | 14.9 | 651.88 | 35.3 | 174.94 | 83.0 |
| USTECm | reversion | wide_va | 220 | -0.533 | -6.83 | 11.4 | 553.71 | 44.6 | 89.25 | 91.1 |
| USTECm | reversion | one_r | 328 | -0.555 | -12.18 | 22.3 | 400.67 | 60.1 | 24.54 | 97.6 |
| USTECm | reversion | hold60 | 328 | -0.530 | -8.03 | 11.6 | 416.20 | 58.4 | 27.68 | 97.2 |
| US500m | trend | base | 1045 | -0.424 | -12.86 | 20.4 | 107.06 | 89.3 | 0.11 | 100.0 |
| US500m | trend | proxy | 16 | -0.287 | -1.41 | 37.5 | 977.16 | 2.3 | 910.18 | 9.0 |
| US500m | trend | first90 | 633 | -0.344 | -7.65 | 24.2 | 333.46 | 66.7 | 10.86 | 98.9 |
| US500m | trend | wide_va | 392 | -0.345 | -5.71 | 21.9 | 505.17 | 49.5 | 59.63 | 94.0 |
| US500m | trend | one_r | 1045 | -0.427 | -15.51 | 28.6 | 106.31 | 89.6 | 0.11 | 100.0 |
| US500m | trend | hold60 | 1045 | -0.434 | -11.82 | 17.1 | 101.47 | 90.1 | 0.08 | 100.0 |
| US500m | reversion | base | 251 | -0.596 | -10.45 | 12.7 | 471.59 | 53.3 | 47.36 | 95.4 |
| US500m | reversion | proxy | 6 | -1.000 | — | 0.0 | 970.37 | 3.0 | 885.84 | 11.4 |
| US500m | reversion | first90 | 122 | -0.447 | -4.51 | 18.9 | 759.56 | 25.1 | 324.68 | 69.2 |
| US500m | reversion | wide_va | 137 | -0.535 | -5.82 | 14.6 | 691.68 | 30.8 | 222.40 | 77.8 |
| US500m | reversion | one_r | 251 | -0.562 | -11.15 | 21.9 | 492.78 | 51.5 | 56.88 | 94.7 |
| US500m | reversion | hold60 | 251 | -0.576 | -9.38 | 10.8 | 483.16 | 52.2 | 51.98 | 95.0 |
| DE30m | trend | base | 779 | -0.406 | -9.82 | 19.4 | 203.14 | 81.2 | 1.44 | 99.9 |
| DE30m | trend | proxy | 16 | -0.242 | -1.20 | 37.5 | 980.67 | 2.6 | 923.40 | 10.0 |
| DE30m | trend | first90 | 505 | -0.343 | -6.17 | 20.6 | 416.09 | 62.6 | 26.52 | 98.2 |
| DE30m | trend | wide_va | 187 | -0.313 | -3.77 | 21.4 | 743.67 | 25.6 | 294.46 | 70.6 |
| DE30m | trend | one_r | 779 | -0.422 | -13.23 | 28.6 | 191.34 | 81.4 | 1.20 | 99.9 |
| DE30m | trend | hold60 | 779 | -0.389 | -8.38 | 16.7 | 216.23 | 81.1 | 1.78 | 99.9 |
| DE30m | reversion | base | 391 | -0.423 | -7.81 | 23.0 | 434.43 | 56.6 | 33.02 | 96.7 |
| DE30m | reversion | proxy | 6 | -0.833 | -5.00 | 0.0 | 975.25 | 2.5 | 903.92 | 9.6 |
| DE30m | reversion | first90 | 278 | -0.416 | -6.95 | 24.8 | 558.38 | 44.2 | 92.66 | 90.7 |
| DE30m | reversion | wide_va | 106 | -0.332 | -2.87 | 23.6 | 836.81 | 18.9 | 478.99 | 57.3 |
| DE30m | reversion | one_r | 391 | -0.450 | -10.07 | 27.1 | 412.81 | 58.7 | 27.40 | 97.3 |
| DE30m | reversion | hold60 | 391 | -0.440 | -8.03 | 21.5 | 420.63 | 57.9 | 28.96 | 97.1 |
| XAUUSDm | trend | base | 866 | -0.223 | -4.72 | 20.2 | 372.07 | 63.0 | 15.04 | 98.5 |
| XAUUSDm | trend | proxy | 13 | -0.417 | -1.30 | 15.4 | 973.03 | 4.2 | 893.96 | 16.0 |
| XAUUSDm | trend | first90 | 587 | -0.143 | -2.25 | 21.6 | 646.63 | 35.9 | 143.94 | 85.9 |
| XAUUSDm | trend | wide_va | 178 | -0.251 | -2.30 | 18.5 | 796.16 | 20.5 | 381.11 | 62.1 |
| XAUUSDm | trend | one_r | 866 | -0.185 | -5.54 | 40.6 | 444.72 | 57.3 | 34.36 | 97.1 |
| XAUUSDm | trend | hold60 | 866 | -0.186 | -3.44 | 19.2 | 435.71 | 57.9 | 26.56 | 97.6 |
| XAUUSDm | reversion | base | 305 | -0.408 | -5.69 | 15.1 | 533.07 | 47.1 | 74.89 | 92.8 |
| XAUUSDm | reversion | proxy | 7 | -0.080 | -0.18 | 42.9 | 997.12 | 1.0 | 987.31 | 4.0 |
| XAUUSDm | reversion | first90 | 148 | -0.271 | -2.59 | 20.3 | 815.73 | 22.1 | 427.14 | 64.0 |
| XAUUSDm | reversion | wide_va | 80 | -0.435 | -2.95 | 11.2 | 838.72 | 16.9 | 484.26 | 53.3 |
| XAUUSDm | reversion | one_r | 305 | -0.359 | -6.74 | 32.1 | 576.21 | 43.2 | 105.31 | 90.1 |
| XAUUSDm | reversion | hold60 | 305 | -0.418 | -5.48 | 12.1 | 524.75 | 47.5 | 69.73 | 93.0 |

### 2024-10 to 2026-09

| Market | Model | Rule | N | Avg R | t | Win % | 0.5% € | DD % | 2% € | DD % |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| USTECm | trend | base | 232 | -0.059 | -0.59 | 27.6 | 928.12 | 15.3 | 688.62 | 51.5 |
| USTECm | trend | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| USTECm | trend | first90 | 161 | -0.125 | -1.23 | 26.7 | 901.31 | 15.8 | 634.94 | 51.3 |
| USTECm | trend | wide_va | 102 | -0.120 | -0.77 | 23.5 | 937.49 | 6.6 | 745.46 | 26.6 |
| USTECm | trend | one_r | 232 | -0.132 | -2.03 | 43.5 | 855.19 | 17.8 | 516.61 | 55.8 |
| USTECm | trend | hold60 | 232 | -0.087 | -0.88 | 25.0 | 897.59 | 17.0 | 602.33 | 55.4 |
| USTECm | reversion | base | 57 | -0.590 | -6.52 | 7.0 | 844.79 | 15.5 | 505.80 | 49.4 |
| USTECm | reversion | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| USTECm | reversion | first90 | 24 | -0.515 | -3.26 | 8.3 | 939.83 | 6.0 | 777.83 | 22.2 |
| USTECm | reversion | wide_va | 29 | -0.617 | -4.72 | 3.4 | 914.10 | 8.6 | 695.57 | 30.4 |
| USTECm | reversion | one_r | 57 | -0.333 | -2.65 | 33.3 | 908.72 | 9.6 | 676.07 | 33.7 |
| USTECm | reversion | hold60 | 57 | -0.618 | -7.90 | 7.0 | 838.01 | 16.2 | 490.08 | 51.0 |
| US500m | trend | base | 230 | -0.240 | -3.18 | 24.8 | 756.20 | 24.6 | 312.42 | 68.9 |
| US500m | trend | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| US500m | trend | first90 | 141 | -0.163 | -1.59 | 29.1 | 889.14 | 13.8 | 606.16 | 46.2 |
| US500m | trend | wide_va | 62 | -0.305 | -2.13 | 19.4 | 908.89 | 9.5 | 674.16 | 33.6 |
| US500m | trend | one_r | 230 | -0.174 | -2.68 | 41.3 | 816.55 | 21.0 | 429.50 | 62.3 |
| US500m | trend | hold60 | 230 | -0.222 | -2.48 | 23.0 | 770.73 | 24.8 | 332.10 | 69.5 |
| US500m | reversion | base | 44 | -0.660 | -6.54 | 9.1 | 864.39 | 14.8 | 555.03 | 47.5 |
| US500m | reversion | proxy | 1 | -1.000 | — | 0.0 | 995.00 | 0.5 | 980.00 | 2.0 |
| US500m | reversion | first90 | 13 | -0.465 | -1.78 | 15.4 | 970.07 | 4.4 | 883.77 | 16.6 |
| US500m | reversion | wide_va | 19 | -0.776 | -5.80 | 5.3 | 928.71 | 7.7 | 741.91 | 27.6 |
| US500m | reversion | one_r | 44 | -0.501 | -3.79 | 25.0 | 895.06 | 12.3 | 637.55 | 41.1 |
| US500m | reversion | hold60 | 44 | -0.689 | -7.49 | 6.8 | 859.02 | 14.8 | 541.47 | 47.5 |
| DE30m | trend | base | 237 | -0.182 | -1.95 | 24.5 | 801.04 | 25.9 | 383.77 | 71.0 |
| DE30m | trend | proxy | 3 | 0.105 | 0.18 | 66.7 | 1001.55 | 0.5 | 1005.90 | 2.0 |
| DE30m | trend | first90 | 158 | -0.020 | -0.16 | 28.5 | 979.28 | 11.4 | 867.57 | 39.7 |
| DE30m | trend | wide_va | 40 | -0.270 | -1.63 | 27.5 | 946.99 | 5.3 | 798.82 | 20.1 |
| DE30m | trend | one_r | 237 | -0.244 | -3.93 | 38.0 | 746.51 | 27.4 | 299.96 | 72.9 |
| DE30m | trend | hold60 | 237 | -0.092 | -0.82 | 22.4 | 888.60 | 22.5 | 564.52 | 65.7 |
| DE30m | reversion | base | 111 | -0.398 | -3.77 | 21.6 | 800.27 | 20.0 | 401.06 | 59.9 |
| DE30m | reversion | proxy | 2 | -1.000 | — | 0.0 | 990.03 | 1.0 | 960.40 | 4.0 |
| DE30m | reversion | first90 | 76 | -0.339 | -3.12 | 27.6 | 878.17 | 12.2 | 587.95 | 41.2 |
| DE30m | reversion | wide_va | 17 | -0.188 | -0.72 | 23.5 | 983.94 | 2.6 | 934.66 | 10.3 |
| DE30m | reversion | one_r | 111 | -0.401 | -4.61 | 29.7 | 799.17 | 20.1 | 401.16 | 59.9 |
| DE30m | reversion | hold60 | 111 | -0.377 | -3.31 | 20.7 | 809.27 | 19.1 | 418.21 | 58.2 |
| XAUUSDm | trend | base | 233 | -0.050 | -0.47 | 21.5 | 936.95 | 15.3 | 709.85 | 51.3 |
| XAUUSDm | trend | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| XAUUSDm | trend | first90 | 179 | 0.016 | 0.13 | 21.8 | 1008.09 | 9.7 | 959.44 | 36.3 |
| XAUUSDm | trend | wide_va | 68 | -0.047 | -0.23 | 23.5 | 981.91 | 8.0 | 906.14 | 28.8 |
| XAUUSDm | trend | one_r | 233 | 0.018 | 0.28 | 50.6 | 1018.32 | 7.3 | 1038.66 | 28.2 |
| XAUUSDm | trend | hold60 | 233 | -0.026 | -0.22 | 19.3 | 960.98 | 15.3 | 771.56 | 51.2 |
| XAUUSDm | reversion | base | 82 | -0.439 | -4.13 | 12.2 | 834.41 | 17.2 | 478.30 | 53.7 |
| XAUUSDm | reversion | proxy | 2 | -1.000 | — | 0.0 | 990.03 | 1.0 | 960.40 | 4.0 |
| XAUUSDm | reversion | first90 | 37 | -0.187 | -0.91 | 18.9 | 965.29 | 5.9 | 860.92 | 22.0 |
| XAUUSDm | reversion | wide_va | 28 | -0.580 | -3.46 | 7.1 | 921.71 | 8.7 | 718.43 | 30.7 |
| XAUUSDm | reversion | one_r | 82 | -0.266 | -2.51 | 36.6 | 895.78 | 11.7 | 636.15 | 40.0 |
| XAUUSDm | reversion | hold60 | 82 | -0.540 | -6.10 | 6.1 | 800.70 | 19.9 | 406.43 | 59.4 |

### 2026 Jan-Sep

| Market | Model | Rule | N | Avg R | t | Win % | 0.5% € | DD % | 2% € | DD % |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| USTECm | trend | base | 94 | 0.030 | 0.18 | 33.0 | 1011.35 | 12.5 | 1012.14 | 41.9 |
| USTECm | trend | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| USTECm | trend | first90 | 70 | 0.035 | 0.19 | 34.3 | 1010.26 | 8.2 | 1018.00 | 29.6 |
| USTECm | trend | wide_va | 42 | -0.223 | -1.23 | 26.2 | 953.61 | 6.2 | 819.92 | 23.0 |
| USTECm | trend | one_r | 94 | -0.133 | -1.31 | 43.6 | 938.21 | 11.6 | 764.10 | 39.5 |
| USTECm | trend | hold60 | 94 | 0.042 | 0.24 | 30.9 | 1016.87 | 10.6 | 1030.64 | 37.3 |
| USTECm | reversion | base | 19 | -0.684 | -6.24 | 0.0 | 936.91 | 6.3 | 769.02 | 23.1 |
| USTECm | reversion | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| USTECm | reversion | first90 | 8 | -0.375 | -2.05 | 0.0 | 985.07 | 1.5 | 941.19 | 5.9 |
| USTECm | reversion | wide_va | 11 | -0.636 | -4.18 | 0.0 | 965.52 | 3.4 | 868.13 | 13.2 |
| USTECm | reversion | one_r | 19 | -0.368 | -1.68 | 31.6 | 965.38 | 3.9 | 866.04 | 15.1 |
| USTECm | reversion | hold60 | 19 | -0.684 | -6.24 | 0.0 | 936.91 | 6.3 | 769.02 | 23.1 |
| US500m | trend | base | 93 | -0.240 | -2.07 | 24.7 | 893.23 | 10.9 | 625.48 | 37.7 |
| US500m | trend | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| US500m | trend | first90 | 60 | -0.275 | -2.10 | 25.0 | 920.08 | 8.0 | 709.72 | 29.0 |
| US500m | trend | wide_va | 18 | -0.496 | -3.38 | 11.1 | 956.22 | 4.4 | 834.63 | 16.5 |
| US500m | trend | one_r | 93 | -0.140 | -1.35 | 43.0 | 935.98 | 9.1 | 756.81 | 32.5 |
| US500m | trend | hold60 | 93 | -0.228 | -1.59 | 22.6 | 897.35 | 12.4 | 632.37 | 41.9 |
| US500m | reversion | base | 17 | -0.488 | -2.45 | 17.6 | 959.17 | 4.8 | 844.51 | 18.1 |
| US500m | reversion | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| US500m | reversion | first90 | 6 | -0.216 | -0.50 | 16.7 | 993.47 | 1.5 | 973.30 | 5.9 |
| US500m | reversion | wide_va | 5 | -0.800 | -4.00 | 0.0 | 980.15 | 2.0 | 922.37 | 7.8 |
| US500m | reversion | one_r | 17 | -0.298 | -1.24 | 35.3 | 974.80 | 4.0 | 900.62 | 15.1 |
| US500m | reversion | hold60 | 17 | -0.488 | -2.45 | 17.6 | 959.17 | 4.8 | 844.51 | 18.1 |
| DE30m | trend | base | 89 | 0.053 | 0.30 | 27.0 | 1020.82 | 6.5 | 1047.62 | 23.8 |
| DE30m | trend | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| DE30m | trend | first90 | 63 | 0.215 | 0.92 | 30.2 | 1067.22 | 5.3 | 1258.46 | 19.9 |
| DE30m | trend | wide_va | 18 | -0.289 | -1.00 | 27.8 | 973.96 | 2.6 | 896.27 | 10.4 |
| DE30m | trend | one_r | 89 | -0.069 | -0.65 | 47.2 | 968.67 | 5.3 | 868.97 | 20.1 |
| DE30m | trend | hold60 | 89 | 0.158 | 0.75 | 24.7 | 1068.26 | 6.8 | 1239.82 | 24.6 |
| DE30m | reversion | base | 43 | -0.237 | -1.16 | 23.3 | 949.42 | 5.5 | 803.65 | 21.2 |
| DE30m | reversion | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| DE30m | reversion | first90 | 31 | -0.299 | -1.99 | 25.8 | 954.45 | 5.8 | 826.89 | 21.6 |
| DE30m | reversion | wide_va | 7 | -0.429 | -2.12 | 0.0 | 985.07 | 1.5 | 941.19 | 5.9 |
| DE30m | reversion | one_r | 43 | -0.209 | -1.39 | 39.5 | 955.48 | 5.4 | 828.10 | 20.4 |
| DE30m | reversion | hold60 | 43 | -0.237 | -1.16 | 23.3 | 949.42 | 5.5 | 803.65 | 21.2 |
| XAUUSDm | trend | base | 96 | -0.146 | -1.19 | 20.8 | 930.50 | 9.8 | 734.77 | 34.5 |
| XAUUSDm | trend | proxy | 0 | — | — | — | 1000.00 | 0.0 | 1000.00 | 0.0 |
| XAUUSDm | trend | first90 | 78 | -0.119 | -0.82 | 20.5 | 952.99 | 9.0 | 809.93 | 32.1 |
| XAUUSDm | trend | wide_va | 43 | -0.264 | -2.42 | 16.3 | 944.46 | 6.3 | 792.72 | 23.0 |
| XAUUSDm | trend | one_r | 96 | 0.046 | 0.45 | 52.1 | 1021.31 | 5.7 | 1072.55 | 21.2 |
| XAUUSDm | trend | hold60 | 96 | -0.128 | -0.96 | 18.8 | 938.44 | 10.7 | 757.79 | 37.0 |
| XAUUSDm | reversion | base | 39 | -0.323 | -1.67 | 15.4 | 938.27 | 7.0 | 768.33 | 25.7 |
| XAUUSDm | reversion | proxy | 1 | -1.000 | — | 0.0 | 995.00 | 0.5 | 980.00 | 2.0 |
| XAUUSDm | reversion | first90 | 18 | 0.042 | 0.11 | 27.8 | 1003.26 | 2.7 | 1006.60 | 10.4 |
| XAUUSDm | reversion | wide_va | 18 | -0.457 | -1.84 | 11.1 | 959.42 | 5.0 | 844.45 | 18.5 |
| XAUUSDm | reversion | one_r | 39 | -0.260 | -1.68 | 35.9 | 950.05 | 6.4 | 810.03 | 23.6 |
| XAUUSDm | reversion | hold60 | 39 | -0.488 | -3.06 | 7.7 | 908.67 | 9.1 | 677.09 | 32.3 |

## Random-direction diagnostic

At each baseline candidate time, compare the true direction to a seeded 50/50 reversed-direction trade, both with the same initial risk distance and a 1R target. This isolates directional timing; it does not test POC target skill.

| Market | Model | N | True 1R avg R | Random 1R avg R |
|---|---|---:|---:|---:|
| USTECm | trend | 554 | -0.257 | -0.246 |
| USTECm | reversion | 182 | -0.471 | -0.444 |
| US500m | trend | 550 | -0.300 | -0.300 |
| US500m | reversion | 128 | -0.435 | -0.444 |
| DE30m | trend | 519 | -0.384 | -0.365 |
| DE30m | reversion | 270 | -0.404 | -0.433 |
| XAUUSDm | trend | 536 | -0.080 | -0.167 |
| XAUUSDm | reversion | 184 | -0.282 | -0.369 |

## Verdict

The single training-selected version is **trend / wide_va**. NASDAQ hold-out: 322 trades, -0.282 R/trade, Bonferroni p=0.001. It fails to show positive hold-out expectancy after the quoted spread. Confidence is moderate that this precise CFD implementation lost during the hold-out, but low that the sign will be stable in a new spread regime.

Changing account risk does not change R expectancy: 2% scales the losses and drawdowns in these negative-expectancy variants, while 0.25% would only slow them. The unselected 2026 NASDAQ trend/base row is slightly positive, but its 94-trade t statistic is only 0.18 and does not rescue the full hold-out.

Fabio's claimed edge rests on executed-order aggression, large-trade bubbles, footprint and CVD, none of which exist in these quote data. Tick frequency and quote direction cannot validate that claim. His discretionary identification of balances, swing points and changing market context is also absent. The older-POC trend target is one explicit interpretation of an ambiguous part of the transcript. Conclusions apply only to this TPO/CFD translation, with low confidence about his actual futures method. Spread-era changes and the synthetic 2016–19 asks further limit generalisation.
