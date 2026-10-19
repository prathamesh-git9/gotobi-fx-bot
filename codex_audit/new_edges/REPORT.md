# Scheduled-flow edge audit

**Verdict: no rule is worth automating from this study.** None of the 13 tested ideas has both positive net expectancy and a positive advantage over its control at the 2022–September 2026 holdout threshold. The strongest looking FX result, buying EUR/USD into the month-end London fix, earned 1.61 pips per event but its one-sample t-statistic was only 1.25 (two-sided p = 0.216). Its advantage over ordinary days was nominally significant (p = 0.029), but that does not establish a profitable trade, and it fails the 13-test family threshold of p < 0.00385.

## Flow rationale and sources

The WMR closing FX rate is fixed at **16:00 London time**; month-end benchmark and hedge demand can concentrate orders around it. [LSEG WMR benchmark description](https://www.lseg.com/en/ftse-russell/benchmarks/wmr-fx-benchmarks?lid=q71xl25yipv7). The London gold price auctions are scheduled for **10:30 and 15:00 London time**. [LBMA auction schedule](https://www.lbma.org.uk/prices-and-data/about-lbma-daily-auction-prices). S&P U.S. index share and weight changes occur quarterly around the third Friday of March, June, September and December, which motivates a close-window test. [S&P U.S. Indices methodology](https://www.spglobal.com/spdji/en/documents/methodologies/methodology-sp-us-indices.pdf). These schedules explain why a flow might exist; they do not predict its sign or prove that it exceeds spread.

The additional FX hedge hypothesis is an **inference**, not a documented mechanical trading rule: an increase in U.S. equity exposure might generate month-end USD sales from foreign investors maintaining hedge ratios. I tested its direction using only the prior available SPY close and its 20-trading-day return. Positive SPY return means buy EUR/USD or GBP/USD and sell USD/JPY; negative return reverses that trade. No holdout direction was selected.

## Method

- Source bars: the permitted Exness Standard UTC one-minute bid/ask parquet files. EUR/USD and GBP/USD start in 2019 because the optional 2016–2018 files were absent. USD/JPY starts in 2016. Gold has earlier data, although its rule-selection sample begins in 2016. Index series begin in 2019. Data after **2026-09-30** is excluded. SPY daily closes come only from the permitted `daily_yahoo.parquet` file.
- Rule-selection period: **2016–2021**, or **2019–2021** for the later-starting pairs and indices. For unconditional ideas, select the buy or sell side with the higher event-day mean in that period, even when both sides lose. Evaluate that side once in **2022–2026-09-30**. Conditional SPY directions are fixed by the stated hypothesis.
- FX trades enter at 15:30 London and exit at the **16:00 bar open** on the calendar's last weekday of each month. Gold AM uses 10:00–10:30 London and PM uses 14:30–15:00. U.S. index trades use 15:30–15:59 New York, because a 16:00 bar is often unavailable. Month/quarter-end index tests use the last weekday of the month/quarter. Quarterly index rebalance tests use the third Friday of March, June, September and December.
- Buy at ask open, sell at bid open, close on the opposite side. Each trade has a symmetric stop and target at **15% of the median full-day bid range of the prior 20 observed UTC days**. Scan every intervening minute's correct bid or ask high/low. If stop and target touch in the same minute, book the stop. Require every minute and the exit bar; otherwise skip the event. This includes the observed spread and prevents a missing bar from hiding a stop.
- Controls take the **same side and same clock window on ordinary days**; quarter-end controls exclude all month-ends. Gold uses a paired same-day control at 11:00–11:30 for AM and 13:30–14:00 for PM. The reported event-control t-statistic is Welch's unequal-variance test except for gold, where it is a paired-date test. The event t-statistic tests mean net P&L against zero. All p-values are two-sided and unadjusted in the table; the survival gate uses Bonferroni p < 0.05/13 on **both** tests, with positive t-statistics.
- EUR/USD and GBP/USD numbers are pips (0.0001); USD/JPY numbers are pips (0.01); gold is USD per ounce; indices are index points. Totals are sums of per-trade net price changes, not account P&L. No financing, commission beyond observed spread, latency, market impact, or gap slippage is modeled.

## Every tested idea

`Train` and `Test` show event trade count / mean net result. `Control` is mean net result at the ordinary-day/time comparator. `t (p)` tests event expectancy against zero. `Δt (p)` tests event against control. All results in the instrument units described above.

| Idea | Selected side | Train | Test | Control | t (p) | Δt (p) |
|---|---|---:|---:|---:|---:|---:|
| EUR/USD month-end FX fix | Buy | 36 / 1.72 | 56 / 1.61 | -1.32 | 1.25 (0.216) | 2.24 (0.029) |
| GBP/USD month-end FX fix | Sell | 36 / -0.59 | 57 / -3.56 | -0.79 | -2.33 (0.023) | -1.77 (0.081) |
| USD/JPY month-end FX fix | Buy | 70 / -0.27 | 57 / -2.79 | -0.08 | -1.50 (0.139) | -1.43 (0.158) |
| Gold London AM fix | Sell | 1534 / -0.23 | 1223 / -0.01 | -0.38 | -0.07 (0.946) | 2.50 (0.013) |
| Gold London PM fix | Sell | 1534 / -0.31 | 1224 / -0.25 | -0.20 | -1.34 (0.179) | -0.15 (0.878) |
| US500 month-end close | Buy | 17 / 3.84 | 33 / 0.46 | -0.92 | 0.32 (0.751) | 0.94 (0.354) |
| US500 quarter-end close | Buy | 5 / 5.42 | 9 / 1.77 | -0.92 | 0.62 (0.553) | 0.94 (0.376) |
| USTEC quarter-end close | Buy | 5 / 25.97 | 9 / 12.38 | -1.61 | 1.00 (0.347) | 1.12 (0.294) |
| EUR/USD month-end SPY hedge | SPY conditional | 36 / 0.51 | 56 / -0.28 | -0.65 | -0.21 (0.834) | 0.27 (0.788) |
| GBP/USD month-end SPY hedge | SPY conditional | 36 / 1.02 | 57 / 1.55 | -0.74 | 0.98 (0.331) | 1.42 (0.161) |
| USD/JPY month-end SPY hedge | SPY conditional | 70 / -3.35 | 57 / 1.28 | -0.82 | 0.68 (0.502) | 1.09 (0.281) |
| US500 quarterly index rebalance | Sell | 5 / 5.62 | 9 / -4.23 | -1.10 | -1.30 (0.230) | -0.96 (0.367) |
| USTEC quarterly index rebalance | Sell | 6 / 11.90 | 9 / -12.42 | -4.16 | -0.79 (0.450) | -0.53 (0.613) |

### Holdout net result by year

Each cell is the sum of net pips (FX), USD/oz (gold), or index points (indices), **not** a compounded return. 2026 ends on September 30. `—` means no qualifying complete trade in that year.

| Idea | 2022 | 2023 | 2024 | 2025 | 2026 Jan–Sep |
|---|---:|---:|---:|---:|---:|
| EUR/USD FX fix | 65.12 | -25.37 | -31.48 | 69.29 | 12.67 |
| GBP/USD FX fix | -47.99 | -14.58 | -2.30 | -116.31 | -21.80 |
| USD/JPY FX fix | -52.25 | -89.29 | 21.17 | -73.37 | 34.46 |
| Gold AM | -100.17 | -47.78 | -52.92 | 42.02 | 149.47 |
| Gold PM | -131.66 | -72.97 | 26.61 | 114.47 | -237.96 |
| US500 month-end | — | -8.06 | -18.01 | 34.11 | 7.15 |
| US500 quarter-end | — | — | -5.73 | 37.30 | -15.62 |
| USTEC quarter-end | 43.61 | — | -28.32 | 116.53 | -20.42 |
| EUR/USD SPY hedge | -60.12 | -1.22 | 11.83 | 54.08 | -20.29 |
| GBP/USD SPY hedge | 43.01 | -1.33 | 27.86 | 72.17 | -53.58 |
| USD/JPY SPY hedge | 41.95 | 61.71 | 24.49 | -77.21 | 21.89 |
| US500 rebalance | — | — | -11.94 | -31.40 | 5.31 |
| USTEC rebalance | — | — | 4.57 | -135.73 | 19.40 |

### Rule-selection net result by year

Same units as above. The index series have no qualifying 2021 event window under the strict complete-bar rule for the quarterly tests.

| Idea | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 |
|---|---:|---:|---:|---:|---:|---:|
| EUR/USD FX fix | — | — | — | 16.75 | 28.70 | 16.33 |
| GBP/USD FX fix | — | — | — | -78.90 | 50.09 | 7.43 |
| USD/JPY FX fix | -83.48 | 49.44 | -9.30 | -3.13 | 6.49 | 20.78 |
| Gold AM | -73.38 | -69.31 | -71.46 | -74.93 | -77.85 | 20.33 |
| Gold PM | -123.87 | -78.73 | -34.32 | -82.51 | -160.04 | 10.39 |
| US500 month-end | — | — | — | 2.54 | 51.36 | 11.39 |
| US500 quarter-end | — | — | — | -3.83 | 30.93 | — |
| USTEC quarter-end | — | — | — | 1.87 | 127.98 | — |
| EUR/USD SPY hedge | — | — | — | 19.70 | -4.66 | 3.25 |
| GBP/USD SPY hedge | — | — | — | 76.20 | 38.40 | -77.77 |
| USD/JPY SPY hedge | 67.95 | -46.00 | -70.03 | -47.87 | -88.63 | -50.13 |
| US500 rebalance | — | — | — | 0.25 | 27.87 | — |
| USTEC rebalance | — | — | — | -4.17 | 75.59 | — |

## Survivors and compounding

**Survivors: none.** The requested EUR 1,000 / USD-equivalent compounding results for inception-to-2026 and 2025-to-2026 therefore have no qualifying strategy, final balance, drawdown, trade count, or worst year to report. The code contains the specified calculation at **0.5% of current equity risked per stop** and would produce both horizons automatically if a rule cleared the gate. Reporting growth for a failed rule as a successful edge would be misleading.

## Limits that matter

The calendar uses the last **weekday**, not a full exchange holiday calendar. Holidays or early closes can remove the true last trading session. Complete-window filtering also removes many index observations; the quarter-end and rebalance index holdouts have only **9 trades** each, and some years have none. They are far too thin for a reliable positive claim. Exness index CFDs are proxies for the underlying cash close and rebalance flow.

The intrabar stop fill assumes execution at the stop even if the next bar opens beyond it. That is optimistic during jumps. The study uses observed quote spread but no execution delay or market impact. Daily gold trades can be serially dependent, so their ordinary t-tests may overstate precision. Multiple hypotheses overlap, and the Bonferroni gate is conservative but does not fix every dependence or regime issue.

I inspected the first eight holdout results before adding the three SPY-conditioned ideas and the two third-Friday rebalance ideas. I also changed the index exit from 16:00 to 15:59 after discovering missing 16:00 bars; that change was based on data coverage, not better returns. Consequently the later ideas are **exploratory, not a pristine one-shot holdout**. Their uniformly weak results do not alter the verdict. Fresh future data and independent execution checks would be needed before any of these ideas could be promoted.

Reproduce with `python research.py` in this folder. Machine-readable results are in `results.json`.
