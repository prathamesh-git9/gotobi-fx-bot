# GBP/USD month-end London fix audit

**Verdict: REAL EDGE in these historical bars.** The fixed GBP/USD rule made **+4.30 pips per trade** across 248 observed month ends from January 2006 through September 2026. The mean was positive in each requested era, every tested timing and cost variation, and after removing the five best trades. Same-time trading on other business days lost money. This is evidence for a historical month-end pattern, not a promise of a live fill or a uniquely sterling-driven mechanism.

## Rule and data treatment

- Last London business day of each month, using `holidays.UK` and London daylight saving time. Buy the **15:45 bar open ask**, sell the **16:00 bar open bid**. A bid low at or below entry ask minus 25 pips in the 15:45–15:59 bars exits at exactly −25 pips. No future bar enters the stop check.
- Exness Standard bid/ask bars are used from 2016. For 2006–2015 HistData bid-only bars, ask = bid + **1.5 pips for GBP/USD** and **1.0 pip for EUR/USD**. Those are the respective median 15:45 Exness spreads over 2016–2021, across available days; GBP/USD 10th/90th percentiles were 1.0/1.6 pips, EUR/USD 1.0/1.3. The +0.5 and +1 pip tests increase the entry spread on **all** years, including the modeled period. The historical ask is still an estimate, and its true tail behavior cannot be recovered from bid bars.
- Reported *t* is the one-sample mean divided by its standard error; 95% intervals use a Student *t* distribution. They describe sampling uncertainty under an independent-trade approximation. Pips already include the entry spread. There are no commissions or financing charges modeled.
- One GBP/USD month end, **2016-03-31**, has no complete entry/exit trade in the supplied bars; one EUR/USD month end, **2026-03-31**, is likewise absent. The GBP/USD 2006-09-29 and EUR/USD 2006-09-29 and 2007-10-31 intervals each have one missing minute, so the recorded stop test cannot see a touch within that minute. The GBP/USD 2026 files overlap in 58,194 relevant timestamps; matching bid/ask fields agree exactly, and the primary combined file is retained. The sample ends 2026-09-30 even though two source files extend into October.

## Fixed rule results

| GBP/USD period | Trades | Mean pips | Total pips | *t* | Win rate | 95% interval for mean |
|---|---:|---:|---:|---:|---:|---:|
| 2006–2015 | 120 | +5.16 | +618.9 | 2.61 | 61.7% | +1.24 to +9.08 |
| 2016–2021 | 71 | +3.85 | +273.0 | 1.40 | 53.5% | −1.62 to +9.31 |
| 2022–Sep 2026 | 57 | +3.06 | +174.7 | 1.27 | 56.1% | −1.77 to +7.90 |
| **All** | **248** | **+4.30** | **+1,066.6** | **3.18** | **58.1%** | **+1.64 to +6.96** |

Since 2016, the combined 128 trades averaged **+3.50 pips**, *t*=1.89, 95% interval **−0.17 to +7.17**. Since January 2025, 21 trades averaged **+7.75 pips**, *t*=1.95, interval **−0.55 to +16.06**. The recent positive means are less precisely estimated than the full-history mean.

| Year | Pips | Year | Pips | Year | Pips |
|---|---:|---|---:|---|---:|
| 2006 | +104.5 | 2013 | +103.9 | 2020 | +78.9 |
| 2007 | +130.5 | 2014 | +60.2 | 2021 | −100.2 |
| 2008 | −69.0 | 2015 | −11.0 | 2022 | +7.6 |
| 2009 | +237.0 | 2016 | +122.3 (11 trades) | 2023 | +20.7 |
| 2010 | +23.0 | 2017 | +209.3 | 2024 | −16.4 |
| 2011 | +33.5 | 2018 | −42.3 | 2025 | +121.1 |
| 2012 | +6.3 | 2019 | +5.0 | 2026 | +41.7 (Jan–Sep) |

## Controls and permutation

| GBP/USD trade set, same execution rule | Trades | Mean pips | *t* | Win rate |
|---|---:|---:|---:|---:|
| Month ends, 15:45–16:00 | 248 | **+4.30** | 3.18 | 58.1% |
| All other London business days, 15:45–16:00 | 5,021 | −1.48 | −8.06 | 44.4% |
| Month ends, 14:45–15:00 | 248 | −2.36 | −3.44 | 39.5% |
| Month ends, 16:15–16:30 | 248 | −2.06 | −2.66 | 39.1% |

For the permutation test, each of **10,000** sets draws, without replacement, the observed month-end trade count from all eligible London business days **within each year**. Zero full-period draws reached the month-end mean; the plus-one tail estimate is **0.00010** (random-set mean −1.20 pips; 95th percentile +0.18). Repeating the same year-stratified test for 2016–2026 and 2025–Sep 2026 also produced zero exceedances in 10,000 draws. This tests a specified calendar-day contrast within the available feed; it does not correct for any earlier search that may have produced the proposed rule.

## Robustness

All variants change one feature at a time and remain on the original UK business month ends unless noted. The baseline is **+4.30 pips/trade**.

| Variation | Trades | Mean pips | *t* |
|---|---:|---:|---:|
| Enter 15:40, exit 16:00 | 248 | +4.40 | 3.04 |
| Enter 15:50, exit 16:00 | 248 | +4.53 | 4.00 |
| Enter 15:45, exit 15:58 | 248 | +2.82 | 2.35 |
| Enter 15:45, exit 16:02 | 248 | +4.29 | 2.95 |
| 15-pip stop | 248 | +3.98 | 3.18 |
| 40-pip stop | 248 | +3.82 | 2.65 |
| No stop | 248 | +2.96 | 1.64 |
| Entry spread +0.5 pip | 248 | +3.37 | 2.50 |
| Entry spread +1 pip | 248 | +2.89 | 2.14 |
| Stopped trades filled 3 pips worse | 248 | +3.74 | 2.67 |
| Remove the five best baseline trades | 243 | +3.14 | 2.47 |
| Last calendar weekday instead of UK business day | 248 | +4.62 | 3.42 |

The alternate weekday definition changes six selected dates because of UK holidays. Its 2016-03-31 candidate has no GBP/USD trade; the reported sample therefore has 248 observations. The five best baseline trades total 304.1 pips; the remaining mean is still positive. In the 2016–2026 subset, +1 pip spread gives **+2.45 pips/trade**, 3-pip stop slippage gives **+2.89**, and no stop gives **+3.07**.

## EUR/USD comparison and interpretation

| EUR/USD period | Trades | Mean pips | *t* | Win rate |
|---|---:|---:|---:|---:|
| 2006–2015 | 120 | −4.96 | −3.83 | 35.0% |
| 2016–2021 | 72 | −0.90 | −0.48 | 48.6% |
| 2022–Sep 2026 | 56 | +2.16 | 1.28 | 57.1% |
| **All** | **248** | **−2.17** | **−2.35** | **44.0%** |

EUR/USD does not reproduce the full-period GBP/USD result. Yet its **2025–Sep 2026** slice averaged **+6.73 pips** over 20 trades, compared with GBP/USD's +7.75 over 21. A fix-related index or portfolio rebalance can generate currency-specific net orders, so a sterling-specific historical imbalance is economically possible. The fixing mechanism alone gives no reason to expect a permanently positive GBP/USD order imbalance, and the recent EUR/USD result argues against a clean sterling-only account. These bars reveal price behavior, not the underlying order flow.

## Risk sizing illustration

Starting with **€1,000**, each trade risks 2% of then-current equity at a 25-pip stop; its equity factor is `1 + 0.02 × (realized pips / 25)`. This is a normalized R-multiple illustration, not an exact EUR account conversion or a broker margin simulation.

| Start through 2026-09-30 | Trades | Final equity | Return | Maximum drawdown |
|---|---:|---:|---:|---:|
| 2016-01-01 | 128 | **€1,404.81** | +40.48% | −13.49% |
| 2025-01-01 | 21 | **€1,136.24** | +13.62% | −5.88% |

The stop model assumes a fill at the stop on a touched minute bar. Real stop execution around a fixing window can slip further, and the bid-only decade cannot verify the historical ask. These are the main limits on turning the measured historical pattern into a live trading claim. The audit is reproducible with `python research.py`; trade-level records and every calculation are in `results.json`.
