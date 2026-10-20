# Technical edge hunt on Exness Standard bid/ask bars

Research completed 20 October 2026. [Frozen rules](RULES.md) · [Executable code](research.py) · [Raw results](results.json) · [Summary CSV](summary.csv) · [Seasonality cells](seasonality.csv) · [Scalp split](scalp_split.csv).

## Direct answer

**No validated technical edge was found.** None of the 292 candidate symbol-rule and seasonality tests has a holdout advantage over the same-entry random-direction control after Bonferroni correction. The design-period FDR screen selected no hour or weekday, all 20 scalp idea-symbol tests lose in the low-spread holdout, and the hourly/daily ML portfolios do not earn a reliable net return.

The **single best research candidate** is the XAUUSD three-day-low pullback in a 200-day uptrend: 170 holdout trades, +0.2333R on average, t=2.20, 49.4% wins, and €1,000→€2,071 with 16.4% maximum drawdown at nominal 2% stop risk. Its 75 recent trades average +0.3421R. Confidence in a *distinct pullback edge* is **low**: its adjusted positive-mean and direction-control p values are both 1.0, and a post-hoc year-matched placebo entering long on other uptrend days averages +0.2540R, above the rule's +0.2333R (5,000 seeded samples; 57.8% equal or exceed the rule). The evidence fits broad gold uptrend exposure better than special timing at a three-day low. This is a research lead, not a funded trading recommendation.

## Execution and inference

Signals and execution follow RULES.md. Buy at observed ask, sell at observed bid, enter next M1/hour/day open after the signal, check adverse stop first, and size each separate rule account to 2% initial-stop risk. Balances start at €1,000 independently in every reported window. The full window begins 2016-10-01 for FX/gold and 2019-08-01 for indices, subject to required lookback and available data; C begins 2024-10-01. Recent is 2024-10-01..2026-09-30. The holdout for A/B/D is 2022-01-01..2026-09-30; C uses 2025-10-01..2026-09-30. A zero-swap assumption applies to overnight daily strategies, with a sensitivity in E. The Bonferroni p column tests rule R minus seeded same-entry random-direction R and adjusts across 292 symbol-rule candidates and B discovery cells. Pooled rows are descriptive combinations, with the same conservative multiplier applied. Trade t tests ignore dependence, so even small nominal p values need caution.

## A. Classic technical setups

Each row is a pooled rule account across its allowed symbols, ordered by entry time. The breakout adaptations, UTC day boundary, and exits are specified in RULES.md.

| Rule | Symbol | Window | Trades | Avg R | t | Wins | €1,000 → | Max DD | Random R | Paired t | Bonf p |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NR4 | ALL | full | 4033 | -0.0486 | -1.27 | 47.9% | <€0.01 | 100.0% | -0.0735 | +1.82 | 1 |
| NR4 | ALL | holdout | 2204 | -0.0107 | -0.82 | 48.5% | €529.78 | 76.8% | -0.0317 | +1.17 | 1 |
| NR4 | ALL | recent | 967 | -0.0052 | -0.26 | 49.4% | €839.15 | 46.2% | -0.0336 | +1.02 | 1 |
| NR7 | ALL | full | 1784 | -0.0087 | -0.63 | 48.8% | €649.70 | 58.7% | -0.0173 | +0.46 | 1 |
| NR7 | ALL | holdout | 960 | -0.0150 | -0.82 | 49.0% | €704.63 | 41.4% | +0.0045 | -0.80 | 1 |
| NR7 | ALL | recent | 400 | -0.0193 | -0.67 | 50.2% | €834.67 | 38.3% | +0.0397 | -1.49 | 1 |
| Inside | ALL | full | 3182 | -0.0638 | -1.32 | 47.5% | <€0.01 | 100.0% | -0.0682 | +0.28 | 1 |
| Inside | ALL | holdout | 1714 | -0.0208 | -1.38 | 47.4% | €428.67 | 72.9% | -0.0220 | +0.05 | 1 |
| Inside | ALL | recent | 733 | -0.0145 | -0.61 | 48.2% | €761.56 | 40.0% | -0.0120 | -0.08 | 1 |
| Williams | ALL | full | 12875 | -0.0148 | -1.15 | 48.3% | <€0.01 | 100.0% | -0.0219 | +0.52 | 1 |
| Williams | ALL | holdout | 7010 | +0.0060 | +0.81 | 49.2% | €1,364.92 | 75.3% | -0.0241 | +2.99 | 0.406 |
| Williams | ALL | recent | 2951 | +0.0144 | +1.27 | 49.2% | €1,874.39 | 64.7% | -0.0102 | +1.60 | 1 |
| TurtleSoup | ALL | full | 1762 | -0.0368 | -1.42 | 42.3% | €181.32 | 92.0% | -0.0322 | -0.14 | 1 |
| TurtleSoup | ALL | holdout | 979 | -0.0814 | -2.43 | 39.6% | €163.86 | 88.3% | -0.0739 | -0.18 | 1 |
| TurtleSoup | ALL | recent | 399 | -0.0412 | -0.75 | 41.1% | €655.54 | 49.6% | -0.0314 | -0.15 | 1 |
| Donchian20 | ALL | full | 617 | -0.0246 | -0.39 | 32.1% | €554.15 | 65.1% | -0.1567 | +1.86 | 1 |
| Donchian20 | ALL | holdout | 343 | +0.0550 | +0.64 | 35.6% | €1,234.98 | 50.1% | -0.1605 | +2.29 | 1 |
| Donchian20 | ALL | recent | 144 | -0.1050 | -0.81 | 32.6% | €692.05 | 48.4% | -0.2066 | +0.78 | 1 |
| Donchian55 | ALL | full | 353 | -0.0229 | -0.24 | 28.0% | €684.32 | 50.7% | +0.1282 | -1.78 | 1 |
| Donchian55 | ALL | holdout | 206 | -0.0391 | -0.30 | 26.7% | €746.87 | 50.7% | +0.0575 | -0.95 | 1 |
| Donchian55 | ALL | recent | 91 | -0.1666 | -0.81 | 18.7% | €691.98 | 50.7% | +0.1270 | -2.05 | 1 |
| MA50_200 | ALL | full | 690 | +0.1181 | +1.67 | 33.0% | €3,244.85 | 52.5% | +0.0156 | +1.36 | 1 |
| MA50_200 | ALL | holdout | 408 | +0.1206 | +1.25 | 30.9% | €1,992.51 | 52.5% | +0.0456 | +0.75 | 1 |
| MA50_200 | ALL | recent | 191 | -0.0320 | -0.27 | 31.4% | €799.76 | 52.5% | +0.0809 | -0.75 | 1 |
| Pullback | ALL | full | 1167 | +0.1221 | +2.96 | 42.9% | €10,966.28 | 47.5% | -0.0457 | +3.37 | 0.114 |
| Pullback | ALL | holdout | 740 | +0.1044 | +2.04 | 42.2% | €3,542.26 | 47.5% | -0.0652 | +2.78 | 0.825 |
| Pullback | ALL | recent | 371 | +0.0833 | +1.17 | 42.3% | €1,618.28 | 42.6% | -0.0999 | +2.13 | 1 |
| LondonAsian | ALL | full | 7417 | -0.0603 | -2.67 | 25.6% | <€0.01 | 100.0% | -0.0645 | +0.17 | 1 |
| LondonAsian | ALL | holdout | 3769 | -0.0723 | -2.32 | 25.9% | €0.32 | 100.0% | -0.0736 | +0.04 | 1 |
| LondonAsian | ALL | recent | 1491 | -0.0165 | -0.35 | 29.0% | €235.54 | 92.3% | -0.0591 | +0.77 | 1 |

**Verdict:** NR4, NR7, inside-day, Turtle Soup and London/Asian breakouts lose on average in the holdout. Williams is slightly positive pooled (+0.0060R) with a 75.3% drawdown and no adjusted significance. Donchian 20 and MA50/200 are positive pooled in 2022–2026 but negative in the recent window; Donchian 55 loses. The pooled 200-day-uptrend pullback is positive (+0.1044R holdout), driven especially by gold, but does not pass the multiple-test or timing-placebo checks. All daily overnight figures here assume eligible zero-swap status; see E.

The **full-period NR4, inside-day and Williams compounded balances are contaminated by one supplied USDJPY bar**: at 2019-04-15 06:28 UTC its bid open is 55.920 while surrounding quotes are near 111.94. The prescribed worse-open stop fill produces about −150R for an affected long trade and zeros a 2%-risk account. I retained the raw-feed result and disclose it rather than silently deleting a bad print; its full-period balance is not a reliable economic estimate. The recent and holdout accounts restart after that bar. No A result passes the Bonferroni direction-control test.

## B. UTC hour and weekday seasonality

The design scan contained 194 instrument-hour/weekday cells. Benjamini-Hochberg q=0.05 was applied across the entire design scan before the holdout. The complete net-after-spread map, including unselected cells, is in [seasonality.csv](seasonality.csv).

No hour or weekday cell passed the design FDR screen; no B trade was placed in the holdout.

**Verdict:** No seasonality trade qualified. The strongest unadjusted design cells were USTEC Monday long (one-sided p=0.0054) and US500 Monday long (p=0.0178), but neither survives FDR across 194 cells. Their holdout returns are in the map for audit only; selecting them now would use the test sample. The FDR implementation was corrected to use a one-sided *positive* test after inspecting design selections and before inspecting holdout returns.

## C. One to fifteen minute scalps at low-era spread plus slippage

Each named variant is fixed across four symbols. Full and recent are the same 2024-10..2026-09 low-spread interval for C. The table separates design (2024-10..2025-09) from the single untouched test (2025-10..2026-09). The complete per-symbol full/recent figures are in the appendix.

| Rule | Symbol | Window | Trades | Avg R | t | Wins | €1,000 → | Max DD | Random R | Paired t | Bonf p |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AfterHour_1m | ALL | design | 23594 | -0.4278 | -87.55 | 20.3% | <€0.01 | 100.0% | -0.4259 | -0.31 | 1 |
| AfterHour_1m | ALL | test | 23517 | -0.4066 | -73.07 | 21.4% | <€0.01 | 100.0% | -0.3992 | -1.11 | 1 |
| CashOpen_5m | ALL | design | 1031 | -0.2890 | -6.20 | 24.3% | €1.64 | 99.9% | -0.2748 | -0.28 | 1 |
| CashOpen_5m | ALL | test | 1026 | -0.1885 | -3.52 | 24.7% | €11.77 | 99.0% | -0.3134 | +2.14 | 1 |
| ExtremeFade_3m | ALL | design | 40233 | -0.3678 | -78.87 | 25.5% | <€0.01 | 100.0% | -0.3789 | +1.92 | 1 |
| ExtremeFade_3m | ALL | test | 39771 | -0.3454 | -69.52 | 26.2% | <€0.01 | 100.0% | -0.3533 | +1.28 | 1 |
| MicroBreak30_15m | ALL | design | 45100 | -0.2446 | -43.79 | 31.0% | <€0.01 | 100.0% | -0.2399 | -0.72 | 1 |
| MicroBreak30_15m | ALL | test | 44350 | -0.2252 | -40.47 | 32.1% | <€0.01 | 100.0% | -0.2249 | -0.05 | 1 |
| TickBurst_5m | ALL | design | 20589 | -0.3256 | -35.15 | 23.9% | <€0.01 | 100.0% | -0.3206 | -0.50 | 1 |
| TickBurst_5m | ALL | test | 20128 | -0.3206 | -35.09 | 24.5% | <€0.01 | 100.0% | -0.3108 | -0.97 | 1 |

**Verdict:** All five fixed ideas lose in the 2025-10..2026-09 test even after US index spreads fell, with pooled means from −0.1885R to −0.4066R. Every one of the 20 individual idea-symbol test means is negative. This includes the extra 0.1-pip EURUSD or 0.2-bp gold/index slippage per side. A directional effect occasionally beats a losing random-direction control, but the trade remains unprofitable.

## D. Walk-forward gradient boosting

A new HistGradientBoosting model was fit at each calendar-year boundary using prior years only. The 0.55/0.45 probability threshold, features and risk rules were frozen before the run; yearly fit and signal counts are in results.json.

| Rule | Symbol | Window | Trades | Avg R | t | Wins | €1,000 → | Max DD | Random R | Paired t | Bonf p |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| ML_1h | ALL | full | 49713 | -0.1083 | -36.99 | 41.0% | <€0.01 | 100.0% | -0.1206 | +3.17 | 0.226 |
| ML_1h | ALL | holdout | 18563 | -0.0909 | -19.14 | 42.4% | <€0.01 | 100.0% | -0.1090 | +2.91 | 0.535 |
| ML_1h | ALL | recent | 6166 | -0.0598 | -7.42 | 45.2% | €0.38 | 100.0% | -0.0949 | +3.28 | 0.152 |
| ML_24h | ALL | full | 16485 | -0.0320 | -2.84 | 35.9% | <€0.01 | 100.0% | -0.0521 | +1.49 | 1 |
| ML_24h | ALL | holdout | 9476 | -0.0035 | -0.23 | 36.8% | €9.40 | 99.8% | -0.0301 | +1.48 | 1 |
| ML_24h | ALL | recent | 3854 | +0.0167 | +0.71 | 37.8% | €728.69 | 92.8% | +0.0235 | -0.24 | 1 |

**Verdict:** The 1-hour model averages −0.0909R over 18,563 holdout trades; the 24-hour model averages −0.0035R over 9,476. The latter has a recent +0.0167R but its same-entry random-direction control is +0.0235R, and the compounded account loses. Yearly retraining adapts to new data without changing the frozen features or threshold; it does not create a tradeable edge here.

## E. Overnight financing and swap-free eligibility

Exness says swap-free status is shared across account types, including Standard -m, and currently lists EURUSD, GBPUSD, USDJPY, XAUUSD, and all indices as eligible instruments. Its help page says accounts are swap-free by default but qualification depends on trading activity; persistent large overnight positions can cause status loss. Status must be checked in the Personal Area. [Swap-free status](https://get.exness.help/hc/en-us/articles/4402341895570-Swap-free-status), [Standard account](https://get.exness.help/hc/en-us/articles/17537782738460-Standard-account), [account suffixes](https://get.exness.help/hc/en-us/articles/360014560220-Account-type-suffixes).

Where swap applies, Exness describes daily charges or credits, Wednesday triple swap for FX/metals, Friday triple swap for indices, and rates that can change. Historical account-specific rates are unavailable in this data. [Exness swap schedule and formula](https://get.exness.help/hc/en-us/articles/360014709151-About-swap), [client agreement](https://www.exness.com/cdn/media/exnesssc/exness_sc_client_agreement.pdf).

The A trend rows above are the requested zero-swap rerun: identical price executions and zero financing. The following sensitivity subtracts an assumed 0.01% of notional per calendar day from Donchian, MA and pullback trades; this is **not** a quoted Exness rate.

| Rule | Window | Trades | Avg R after debit | t | Wins | €1,000 → | Max DD |
|---|---|---:|---:|---:|---:|---:|---:|
| Donchian20 | full | 617 | -0.1673 | -2.82 | 28.5% | €97.98 | 90.7% |
| Donchian20 | holdout | 343 | -0.0767 | -0.94 | 31.8% | €508.44 | 51.1% |
| Donchian20 | recent | 144 | -0.2383 | -1.92 | 27.8% | €473.24 | 56.6% |
| Donchian55 | full | 353 | -0.2002 | -2.21 | 25.8% | €200.06 | 82.7% |
| Donchian55 | holdout | 206 | -0.1988 | -1.64 | 24.3% | €391.27 | 60.9% |
| Donchian55 | recent | 91 | -0.3140 | -1.60 | 17.6% | €531.47 | 54.1% |
| MA50_200 | full | 690 | -0.0666 | -1.00 | 31.3% | €266.17 | 90.4% |
| MA50_200 | holdout | 408 | -0.0347 | -0.38 | 29.4% | €576.21 | 74.9% |
| MA50_200 | recent | 191 | -0.1739 | -1.51 | 29.8% | €468.69 | 58.3% |
| Pullback | full | 1167 | +0.0890 | +2.18 | 42.7% | €5,127.15 | 32.9% |
| Pullback | holdout | 740 | +0.0717 | +1.42 | 41.9% | €2,200.77 | 32.7% |
| Pullback | recent | 371 | +0.0524 | +0.74 | 41.8% | €1,290.81 | 33.4% |
| Pullback XAUUSD | full | 340 | +0.1262 | +1.70 | 46.8% | €2,081.70 | 28.0% |
| Pullback XAUUSD | holdout | 170 | +0.2010 | +1.91 | 48.8% | €1,859.13 | 17.0% |
| Pullback XAUUSD | recent | 75 | +0.3137 | +1.94 | 50.7% | €1,554.11 | 14.2% |

**Verdict:** Zero swap is possible for a qualified Standard account on these instruments, but not guaranteed for a strategy that routinely holds overnight. In the zero-swap holdout, Donchian 20 is +0.0550R, MA50/200 +0.1206R and pooled pullback +0.1044R. Under the illustrative 0.01%-of-notional-per-calendar-day debit, those become −0.0767R, −0.0347R and +0.0717R, respectively. Gold pullback remains +0.2010R under that debit, but the matched uptrend-long timing control already removes its apparent special entry advantage. Actual financing depends on live account status, instrument, direction and dates; these estimates are sensitivity tests, not historical Exness charges.

## Limits and forward test

* **Costs and fills.** The supplied minute bid/ask feed gives quote-based fills, not a real order queue. A/B/D include spread but no added latency or slippage; C includes the specified extra slippage. Market orders, stop fills, contract limits, currency conversion, minimum lot and margin could worsen live results. Stops in a bar take priority over time exits, and opening gaps fill at the worse open. The 2% compounding is an unconstrained stress illustration; pooled symbol entries can overlap in real time.
* **Data quality.** The 2019 USDJPY quote error above creates unrealistic full-window ruin for three rules. It was found after the holdout summary was inspected; the frozen results were **not** repaired or retuned. The USTEC file ends 2026-09-29. Minute OHLC cannot reconstruct the actual tick path or execution inside a minute.
* **Inference.** Trade t values assume independent observations despite serial correlation and shared market days. The 292-test Bonferroni adjustment is conservative but does not undo broad research choice, regime changes, or the post-hoc gold timing diagnostic. The first-pass classic trigger and scalp horizon implementations were corrected before any holdout return was read; the B one-sided FDR correction used design selections only. The final rule set is in RULES.md. No holdout return was used to set a strategy parameter. The gold timing placebo was added *after* viewing the holdout and is explicitly exploratory. The matched-year placebo samples eligible uptrend long entries with replacement and ignores overlapping holds, so it tests average timing, not an executable account.
* **Scope.** These are adaptations of the named classic setups to UTC-day Exness CFDs and next-bar market execution. Failure here does not refute published results for futures, equities, or other contract terms.

**Forward test:** Freeze the XAUUSD pullback exactly as written, check live Standard swap-free status each day, and record demo or tiny-size ask/bid fills, rejection, spread, slippage and financing for at least 150 new qualifying entries. In parallel, preselect the same number of year-matched long entries on all other SMA200-uptrend days with the identical five-day hold and stop. Require positive net R, an advantage over that timing control and over same-entry random directions, and a predeclared familywise threshold before calling it an edge. At the historical signal rate this may take several years; a shorter positive run is not confirmation. No funded 2%-risk forward account is justified by the present evidence.

## Appendix: every symbol-rule full and recent result

For C, both windows represent the low-spread era and are identical; its actual design/test split is in section C and scalp_split.csv. All R figures include observed spread, and C also includes stipulated extra slippage.

| Rule | Symbol | Window | Trades | Avg R | t | Wins | €1,000 → | Max DD | Random R | Paired t | Bonf p |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AfterHour_1m | EURUSD | full | 12110 | -0.4933 | -102.42 | 13.3% | <€0.01 | 100.0% | -0.4767 | -2.63 | 1 |
| AfterHour_1m | EURUSD | recent | 12110 | -0.4933 | -102.42 | 13.3% | <€0.01 | 100.0% | -0.4767 | -2.63 | 1 |
| AfterHour_1m | US500 | full | 11704 | -0.4393 | -70.04 | 18.6% | <€0.01 | 100.0% | -0.4422 | +0.38 | 1 |
| AfterHour_1m | US500 | recent | 11704 | -0.4393 | -70.04 | 18.6% | <€0.01 | 100.0% | -0.4422 | +0.38 | 1 |
| AfterHour_1m | USTEC | full | 11686 | -0.3882 | -47.72 | 24.2% | <€0.01 | 100.0% | -0.3957 | +0.78 | 1 |
| AfterHour_1m | USTEC | recent | 11686 | -0.3882 | -47.72 | 24.2% | <€0.01 | 100.0% | -0.3957 | +0.78 | 1 |
| AfterHour_1m | XAUUSD | full | 11611 | -0.3449 | -35.89 | 27.6% | <€0.01 | 100.0% | -0.3330 | -1.06 | 1 |
| AfterHour_1m | XAUUSD | recent | 11611 | -0.3449 | -35.89 | 27.6% | <€0.01 | 100.0% | -0.3330 | -1.06 | 1 |
| CashOpen_5m | EURUSD | full | 516 | -0.3693 | -8.69 | 27.7% | €19.82 | 98.1% | -0.3959 | +0.50 | 1 |
| CashOpen_5m | EURUSD | recent | 516 | -0.3693 | -8.69 | 27.7% | €19.82 | 98.1% | -0.3959 | +0.50 | 1 |
| CashOpen_5m | US500 | full | 513 | -0.3234 | -4.45 | 18.7% | €27.49 | 97.8% | -0.3499 | +0.34 | 1 |
| CashOpen_5m | US500 | recent | 513 | -0.3234 | -4.45 | 18.7% | €27.49 | 97.8% | -0.3499 | +0.34 | 1 |
| CashOpen_5m | USTEC | full | 512 | -0.2110 | -2.20 | 16.0% | €73.72 | 93.6% | -0.2780 | +0.66 | 1 |
| CashOpen_5m | USTEC | recent | 512 | -0.2110 | -2.20 | 16.0% | €73.72 | 93.6% | -0.2780 | +0.66 | 1 |
| CashOpen_5m | XAUUSD | full | 516 | -0.0519 | -0.84 | 35.5% | €480.03 | 56.4% | -0.1526 | +1.47 | 1 |
| CashOpen_5m | XAUUSD | recent | 516 | -0.0519 | -0.84 | 35.5% | €480.03 | 56.4% | -0.1526 | +1.47 | 1 |
| Donchian20 | DE30 | full | 66 | -0.2711 | -1.84 | 24.2% | €685.85 | 35.0% | -0.0845 | -1.07 | 1 |
| Donchian20 | DE30 | recent | 19 | -0.1005 | -0.32 | 36.8% | €956.36 | 15.0% | -0.3989 | +0.72 | 1 |
| Donchian20 | EURUSD | full | 106 | -0.0942 | -0.75 | 34.0% | €791.11 | 33.4% | -0.2628 | +1.07 | 1 |
| Donchian20 | EURUSD | recent | 20 | +0.1199 | +0.40 | 50.0% | €1,042.14 | 11.0% | -0.7085 | +4.03 | 0.104 |
| Donchian20 | GBPUSD | full | 115 | -0.2192 | -2.23 | 33.0% | €588.31 | 46.2% | -0.1167 | -0.92 | 1 |
| Donchian20 | GBPUSD | recent | 24 | -0.3202 | -1.73 | 37.5% | €853.87 | 22.6% | -0.2125 | -0.46 | 1 |
| Donchian20 | US500 | full | 73 | -0.1355 | -1.00 | 30.1% | €804.99 | 25.3% | -0.2218 | +0.53 | 1 |
| Donchian20 | US500 | recent | 24 | -0.4495 | -2.08 | 16.7% | €801.01 | 19.9% | -0.0461 | -1.37 | 1 |
| Donchian20 | USDJPY | full | 100 | +0.0701 | +0.37 | 29.0% | €1,074.48 | 37.2% | -0.3045 | +1.73 | 1 |
| Donchian20 | USDJPY | recent | 19 | -0.3218 | -1.20 | 26.3% | €880.31 | 15.6% | -0.4231 | +0.45 | 1 |
| Donchian20 | USTEC | full | 65 | +0.1282 | +0.70 | 38.5% | €1,149.78 | 14.9% | +0.0014 | +0.62 | 1 |
| Donchian20 | USTEC | recent | 21 | -0.2259 | -0.74 | 23.8% | €902.35 | 14.4% | -0.1311 | -0.27 | 1 |
| Donchian20 | XAUUSD | full | 92 | +0.3527 | +1.45 | 34.8% | €1,745.63 | 16.8% | -0.0357 | +1.53 | 1 |
| Donchian20 | XAUUSD | recent | 17 | +0.8074 | +1.09 | 41.2% | €1,278.05 | 6.9% | +0.5293 | +0.45 | 1 |
| Donchian55 | DE30 | full | 38 | -0.3369 | -1.53 | 23.7% | €763.26 | 27.0% | -0.2403 | -0.39 | 1 |
| Donchian55 | DE30 | recent | 14 | -0.4845 | -1.05 | 7.1% | €866.20 | 20.3% | -0.2556 | -1.00 | 1 |
| Donchian55 | EURUSD | full | 64 | -0.1645 | -0.82 | 23.4% | €784.74 | 39.5% | +0.3458 | -2.25 | 1 |
| Donchian55 | EURUSD | recent | 11 | +0.2022 | +0.28 | 18.2% | €1,033.90 | 13.0% | +1.0170 | -1.96 | 1 |
| Donchian55 | GBPUSD | full | 65 | -0.3226 | -2.17 | 24.6% | €644.88 | 38.1% | -0.2087 | -0.70 | 1 |
| Donchian55 | GBPUSD | recent | 17 | -0.6348 | -3.23 | 11.8% | €803.08 | 20.0% | -0.3434 | -1.20 | 1 |
| Donchian55 | US500 | full | 39 | +0.1027 | +0.41 | 41.0% | €1,063.58 | 13.6% | +0.1168 | -0.05 | 1 |
| Donchian55 | US500 | recent | 14 | -0.2369 | -0.68 | 28.6% | €931.62 | 9.6% | +0.5062 | -1.83 | 1 |
| Donchian55 | USDJPY | full | 58 | +0.0467 | +0.19 | 27.6% | €1,016.76 | 25.6% | +0.1629 | -0.64 | 1 |
| Donchian55 | USDJPY | recent | 13 | -0.4854 | -1.59 | 15.4% | €878.36 | 13.3% | -0.5549 | +0.15 | 1 |
| Donchian55 | USTEC | full | 40 | +0.0560 | +0.22 | 30.0% | €1,025.44 | 13.0% | +0.0318 | +0.09 | 1 |
| Donchian55 | USTEC | recent | 14 | -0.2210 | -0.53 | 21.4% | €934.14 | 10.4% | -0.3402 | +0.30 | 1 |
| Donchian55 | XAUUSD | full | 49 | +0.5566 | +1.33 | 30.6% | €1,597.68 | 13.8% | +0.6233 | -0.27 | 1 |
| Donchian55 | XAUUSD | recent | 8 | +1.6134 | +1.03 | 37.5% | €1,258.66 | 5.3% | +1.8343 | -0.38 | 1 |
| ExtremeFade_3m | EURUSD | full | 21015 | -0.4435 | -85.43 | 21.1% | <€0.01 | 100.0% | -0.4576 | +2.23 | 1 |
| ExtremeFade_3m | EURUSD | recent | 21015 | -0.4435 | -85.43 | 21.1% | <€0.01 | 100.0% | -0.4576 | +2.23 | 1 |
| ExtremeFade_3m | US500 | full | 19698 | -0.3926 | -63.20 | 23.8% | <€0.01 | 100.0% | -0.4011 | +1.10 | 1 |
| ExtremeFade_3m | US500 | recent | 19698 | -0.3926 | -63.20 | 23.8% | <€0.01 | 100.0% | -0.4011 | +1.10 | 1 |
| ExtremeFade_3m | USTEC | full | 19485 | -0.3214 | -43.04 | 28.1% | <€0.01 | 100.0% | -0.3353 | +1.51 | 1 |
| ExtremeFade_3m | USTEC | recent | 19485 | -0.3214 | -43.04 | 28.1% | <€0.01 | 100.0% | -0.3353 | +1.51 | 1 |
| ExtremeFade_3m | XAUUSD | full | 19806 | -0.2636 | -32.48 | 30.7% | <€0.01 | 100.0% | -0.2647 | +0.11 | 1 |
| ExtremeFade_3m | XAUUSD | recent | 19806 | -0.2636 | -32.48 | 30.7% | <€0.01 | 100.0% | -0.2647 | +0.11 | 1 |
| Inside | DE30 | full | 307 | -0.0159 | -0.38 | 45.0% | €878.68 | 26.1% | -0.0236 | +0.15 | 1 |
| Inside | DE30 | recent | 91 | -0.0677 | -1.01 | 42.9% | €877.66 | 17.9% | -0.0111 | -0.68 | 1 |
| Inside | EURUSD | full | 562 | -0.0354 | -1.35 | 47.3% | €643.32 | 39.9% | -0.0102 | -0.68 | 1 |
| Inside | EURUSD | recent | 114 | -0.0683 | -1.17 | 46.5% | €848.22 | 17.8% | +0.0546 | -1.52 | 1 |
| Inside | GBPUSD | full | 584 | -0.0351 | -1.42 | 47.6% | €636.36 | 39.3% | -0.0598 | +0.74 | 1 |
| Inside | GBPUSD | recent | 122 | -0.0028 | -0.06 | 48.4% | €985.73 | 8.3% | -0.0448 | +0.61 | 1 |
| Inside | US500 | full | 313 | -0.1024 | -2.81 | 42.2% | €512.82 | 50.9% | -0.0392 | -1.48 | 1 |
| Inside | US500 | recent | 101 | -0.0513 | -0.70 | 46.5% | €892.02 | 16.2% | -0.0246 | -0.34 | 1 |
| Inside | USDJPY | full | 582 | -0.2270 | -0.88 | 50.2% | <€0.01 | 100.0% | -0.2680 | +1.14 | 1 |
| Inside | USDJPY | recent | 110 | +0.0557 | +0.96 | 56.4% | €1,121.26 | 11.5% | -0.0365 | +1.22 | 1 |
| Inside | USTEC | full | 311 | -0.0336 | -0.88 | 49.5% | €788.61 | 26.7% | -0.0057 | -0.53 | 1 |
| Inside | USTEC | recent | 97 | -0.0189 | -0.27 | 47.4% | €955.11 | 15.1% | -0.0379 | +0.19 | 1 |
| Inside | XAUUSD | full | 523 | +0.0321 | +1.09 | 48.2% | €1,335.28 | 13.8% | +0.0018 | +0.78 | 1 |
| Inside | XAUUSD | recent | 98 | +0.0465 | +0.70 | 48.0% | €1,086.35 | 7.2% | +0.0163 | +0.32 | 1 |
| LondonAsian | DE30 | full | 1589 | -0.1032 | -2.12 | 24.0% | €12.21 | 99.3% | -0.0302 | -1.30 | 1 |
| LondonAsian | DE30 | recent | 447 | -0.0426 | -0.46 | 25.7% | €495.45 | 61.7% | -0.0105 | -0.29 | 1 |
| LondonAsian | EURUSD | full | 2068 | -0.0614 | -1.47 | 26.3% | €19.42 | 98.3% | -0.0566 | -0.10 | 1 |
| LondonAsian | EURUSD | recent | 376 | -0.0822 | -0.94 | 27.4% | €438.48 | 56.2% | -0.0204 | -0.55 | 1 |
| LondonAsian | GBPUSD | full | 2183 | -0.0307 | -0.69 | 24.5% | €45.39 | 97.5% | -0.0905 | +1.24 | 1 |
| LondonAsian | GBPUSD | recent | 412 | -0.0021 | -0.02 | 27.2% | €726.30 | 73.6% | -0.1755 | +1.66 | 1 |
| LondonAsian | XAUUSD | full | 1577 | -0.0565 | -1.23 | 27.8% | €62.10 | 97.1% | -0.0733 | +0.34 | 1 |
| LondonAsian | XAUUSD | recent | 256 | +0.1023 | +1.03 | 40.2% | €1,492.82 | 26.2% | -0.0136 | +1.12 | 1 |
| MA50_200 | DE30 | full | 76 | +0.1358 | +0.66 | 34.2% | €1,173.75 | 14.6% | -0.2556 | +1.66 | 1 |
| MA50_200 | DE30 | recent | 25 | +0.1321 | +0.38 | 36.0% | €1,053.00 | 14.6% | -0.2234 | +0.76 | 1 |
| MA50_200 | EURUSD | full | 124 | -0.0435 | -0.31 | 32.3% | €846.79 | 37.4% | -0.0298 | -0.08 | 1 |
| MA50_200 | EURUSD | recent | 27 | -0.2025 | -0.80 | 37.0% | €888.45 | 18.8% | -0.0568 | -0.33 | 1 |
| MA50_200 | GBPUSD | full | 122 | -0.0542 | -0.41 | 31.1% | €832.63 | 35.8% | -0.1838 | +0.76 | 1 |
| MA50_200 | GBPUSD | recent | 37 | -0.4606 | -3.11 | 21.6% | €705.88 | 29.9% | -0.0812 | -1.52 | 1 |
| MA50_200 | US500 | full | 69 | +0.2843 | +1.21 | 34.8% | €1,407.95 | 11.6% | +0.2072 | +0.56 | 1 |
| MA50_200 | US500 | recent | 24 | +0.0157 | +0.05 | 29.2% | €995.40 | 11.5% | +0.0089 | +0.03 | 1 |
| MA50_200 | USDJPY | full | 124 | +0.0003 | +0.00 | 29.8% | €920.92 | 27.4% | -0.1498 | +0.75 | 1 |
| MA50_200 | USDJPY | recent | 29 | -0.0674 | -0.24 | 34.5% | €949.32 | 9.6% | -0.5128 | +1.51 | 1 |
| MA50_200 | USTEC | full | 75 | +0.3297 | +1.35 | 32.0% | €1,537.54 | 22.6% | +0.5845 | -0.92 | 1 |
| MA50_200 | USTEC | recent | 32 | -0.1825 | -0.65 | 21.9% | €876.15 | 22.6% | +0.9338 | -2.26 | 1 |
| MA50_200 | XAUUSD | full | 100 | +0.3882 | +1.69 | 39.0% | €1,966.77 | 24.3% | +0.1673 | +1.07 | 1 |
| MA50_200 | XAUUSD | recent | 17 | +1.2069 | +1.70 | 52.9% | €1,462.78 | 7.2% | +0.6085 | +1.08 | 1 |
| ML_1h | DE30 | full | 5836 | -0.1337 | -15.63 | 39.6% | <€0.01 | 100.0% | -0.1260 | -0.68 | 1 |
| ML_1h | DE30 | recent | 812 | -0.0308 | -1.39 | 46.6% | €569.12 | 54.1% | -0.0650 | +1.29 | 1 |
| ML_1h | EURUSD | full | 8350 | -0.0880 | -12.69 | 40.7% | <€0.01 | 100.0% | -0.1079 | +2.18 | 1 |
| ML_1h | EURUSD | recent | 984 | -0.0670 | -3.82 | 44.2% | €252.08 | 76.6% | -0.0742 | +0.30 | 1 |
| ML_1h | GBPUSD | full | 5242 | -0.1040 | -12.37 | 39.4% | €0.01 | 100.0% | -0.1439 | +3.50 | 0.0673 |
| ML_1h | GBPUSD | recent | 534 | -0.1132 | -5.11 | 37.6% | €289.81 | 71.2% | -0.1685 | +1.78 | 1 |
| ML_1h | US500 | full | 7897 | -0.1277 | -16.65 | 39.8% | <€0.01 | 100.0% | -0.1451 | +1.71 | 1 |
| ML_1h | US500 | recent | 948 | +0.0180 | +0.78 | 49.2% | €1,278.03 | 27.9% | -0.0438 | +1.96 | 1 |
| ML_1h | USDJPY | full | 8374 | -0.1438 | -20.02 | 39.9% | <€0.01 | 100.0% | -0.1615 | +1.86 | 1 |
| ML_1h | USDJPY | recent | 1175 | -0.1506 | -7.79 | 40.2% | €26.03 | 97.6% | -0.2102 | +2.53 | 1 |
| ML_1h | USTEC | full | 7500 | -0.0955 | -12.28 | 41.7% | <€0.01 | 100.0% | -0.0901 | -0.52 | 1 |
| ML_1h | USTEC | recent | 793 | -0.0531 | -2.24 | 47.7% | €400.98 | 65.0% | -0.0893 | +1.08 | 1 |
| ML_1h | XAUUSD | full | 6514 | -0.0606 | -7.65 | 45.9% | €0.22 | 100.0% | -0.0664 | +0.54 | 1 |
| ML_1h | XAUUSD | recent | 920 | -0.0165 | -0.83 | 49.6% | €690.30 | 37.3% | -0.0109 | -0.20 | 1 |
| ML_24h | DE30 | full | 1941 | -0.0348 | -1.09 | 36.4% | €122.48 | 94.5% | +0.0002 | -0.91 | 1 |
| ML_24h | DE30 | recent | 529 | +0.0303 | +0.48 | 38.2% | €1,106.66 | 44.9% | +0.0799 | -0.68 | 1 |
| ML_24h | EURUSD | full | 2719 | -0.0753 | -2.81 | 35.3% | €5.90 | 99.6% | -0.0924 | +0.53 | 1 |
| ML_24h | EURUSD | recent | 547 | -0.0750 | -1.16 | 34.4% | €346.71 | 79.9% | -0.0462 | -0.39 | 1 |
| ML_24h | GBPUSD | full | 2445 | -0.0719 | -2.58 | 35.0% | €11.99 | 99.5% | -0.0754 | +0.10 | 1 |
| ML_24h | GBPUSD | recent | 447 | +0.0509 | +0.76 | 40.5% | €1,325.20 | 43.0% | +0.0627 | -0.15 | 1 |
| ML_24h | US500 | full | 2050 | +0.0201 | +0.60 | 36.3% | €915.64 | 79.9% | -0.0815 | +2.63 | 1 |
| ML_24h | US500 | recent | 589 | +0.0086 | +0.15 | 37.9% | €876.71 | 60.7% | -0.0018 | +0.15 | 1 |
| ML_24h | USDJPY | full | 2626 | -0.0133 | -0.46 | 36.7% | €161.33 | 87.5% | -0.0257 | +0.36 | 1 |
| ML_24h | USDJPY | recent | 562 | +0.0250 | +0.41 | 39.0% | €1,054.72 | 50.0% | +0.0625 | -0.51 | 1 |
| ML_24h | USTEC | full | 2118 | -0.0274 | -0.84 | 34.0% | €122.26 | 95.3% | -0.0775 | +1.33 | 1 |
| ML_24h | USTEC | recent | 620 | +0.0193 | +0.32 | 35.3% | €964.75 | 52.5% | -0.0743 | +1.38 | 1 |
| ML_24h | XAUUSD | full | 2586 | -0.0108 | -0.38 | 37.5% | €200.20 | 94.5% | -0.0096 | -0.03 | 1 |
| ML_24h | XAUUSD | recent | 560 | +0.0637 | +1.01 | 40.2% | €1,606.44 | 48.9% | +0.1030 | -0.48 | 1 |
| MicroBreak30_15m | EURUSD | full | 22817 | -0.3547 | -51.86 | 27.0% | <€0.01 | 100.0% | -0.3391 | -1.95 | 1 |
| MicroBreak30_15m | EURUSD | recent | 22817 | -0.3547 | -51.86 | 27.0% | <€0.01 | 100.0% | -0.3391 | -1.95 | 1 |
| MicroBreak30_15m | US500 | full | 22226 | -0.2797 | -36.12 | 29.8% | <€0.01 | 100.0% | -0.2690 | -1.20 | 1 |
| MicroBreak30_15m | US500 | recent | 22226 | -0.2797 | -36.12 | 29.8% | <€0.01 | 100.0% | -0.2690 | -1.20 | 1 |
| MicroBreak30_15m | USTEC | full | 22536 | -0.1944 | -23.77 | 33.0% | <€0.01 | 100.0% | -0.1933 | -0.12 | 1 |
| MicroBreak30_15m | USTEC | recent | 22536 | -0.1944 | -23.77 | 33.0% | <€0.01 | 100.0% | -0.1933 | -0.12 | 1 |
| MicroBreak30_15m | XAUUSD | full | 21871 | -0.1063 | -12.33 | 36.6% | <€0.01 | 100.0% | -0.1245 | +1.82 | 1 |
| MicroBreak30_15m | XAUUSD | recent | 21871 | -0.1063 | -12.33 | 36.6% | <€0.01 | 100.0% | -0.1245 | +1.82 | 1 |
| NR4 | DE30 | full | 453 | -0.0090 | -0.29 | 46.4% | €885.93 | 22.0% | -0.0317 | +0.53 | 1 |
| NR4 | DE30 | recent | 132 | -0.0416 | -0.80 | 45.5% | €887.67 | 19.9% | +0.0349 | -1.02 | 1 |
| NR4 | EURUSD | full | 648 | -0.0367 | -1.50 | 46.5% | €590.89 | 46.2% | -0.0283 | -0.24 | 1 |
| NR4 | EURUSD | recent | 137 | -0.0756 | -1.41 | 46.0% | €804.19 | 27.4% | +0.0900 | -2.24 | 1 |
| NR4 | GBPUSD | full | 643 | -0.0254 | -1.02 | 48.4% | €685.88 | 41.2% | -0.0492 | +0.70 | 1 |
| NR4 | GBPUSD | recent | 130 | +0.0167 | +0.31 | 50.8% | €1,034.18 | 11.4% | -0.0306 | +0.65 | 1 |
| NR4 | US500 | full | 472 | -0.0260 | -0.95 | 48.3% | €756.75 | 32.8% | -0.0547 | +0.75 | 1 |
| NR4 | US500 | recent | 141 | -0.0228 | -0.44 | 52.5% | €927.80 | 20.2% | -0.0910 | +1.00 | 1 |
| NR4 | USDJPY | full | 679 | -0.2092 | -0.94 | 48.6% | <€0.01 | 100.0% | -0.2588 | +1.54 | 1 |
| NR4 | USDJPY | recent | 142 | +0.0188 | +0.36 | 52.1% | €1,043.46 | 14.6% | -0.1048 | +1.60 | 1 |
| NR4 | USTEC | full | 477 | -0.0060 | -0.21 | 50.5% | €910.54 | 21.8% | -0.0354 | +0.74 | 1 |
| NR4 | USTEC | recent | 142 | -0.0267 | -0.52 | 50.7% | €917.08 | 15.5% | -0.0701 | +0.65 | 1 |
| NR4 | XAUUSD | full | 661 | +0.0081 | +0.32 | 47.0% | €1,053.39 | 29.8% | -0.0209 | +0.84 | 1 |
| NR4 | XAUUSD | recent | 143 | +0.0906 | +1.67 | 48.3% | €1,280.24 | 7.6% | -0.0541 | +1.83 | 1 |
| NR7 | DE30 | full | 212 | +0.0274 | +0.71 | 50.0% | €1,108.41 | 7.4% | -0.0135 | +0.80 | 1 |
| NR7 | DE30 | recent | 54 | +0.0480 | +0.62 | 53.7% | €1,049.54 | 5.2% | +0.0697 | -0.22 | 1 |
| NR7 | EURUSD | full | 262 | -0.0693 | -1.89 | 44.3% | €682.53 | 33.1% | -0.0731 | +0.07 | 1 |
| NR7 | EURUSD | recent | 54 | -0.0861 | -1.12 | 50.0% | €908.05 | 14.0% | +0.0067 | -0.85 | 1 |
| NR7 | GBPUSD | full | 270 | -0.0418 | -1.12 | 47.0% | €781.83 | 27.4% | -0.0251 | -0.31 | 1 |
| NR7 | GBPUSD | recent | 49 | -0.0124 | -0.17 | 51.0% | €985.37 | 7.8% | +0.0287 | -0.31 | 1 |
| NR7 | US500 | full | 230 | -0.0148 | -0.43 | 48.7% | €922.43 | 19.0% | -0.0139 | -0.02 | 1 |
| NR7 | US500 | recent | 56 | -0.0129 | -0.16 | 57.1% | €981.49 | 13.9% | +0.0322 | -0.40 | 1 |
| NR7 | USDJPY | full | 296 | +0.0105 | +0.31 | 50.7% | €1,043.13 | 15.5% | +0.0297 | -0.49 | 1 |
| NR7 | USDJPY | recent | 66 | -0.0343 | -0.49 | 51.5% | €951.68 | 12.9% | +0.0409 | -0.76 | 1 |
| NR7 | USTEC | full | 217 | +0.0129 | +0.32 | 51.2% | €1,041.24 | 12.1% | -0.0474 | +1.10 | 1 |
| NR7 | USTEC | recent | 59 | -0.0557 | -0.70 | 47.5% | €932.23 | 9.8% | +0.0426 | -1.04 | 1 |
| NR7 | XAUUSD | full | 297 | +0.0189 | +0.56 | 50.2% | €1,096.38 | 8.9% | +0.0090 | +0.22 | 1 |
| NR7 | XAUUSD | recent | 62 | +0.0200 | +0.27 | 41.9% | €1,020.71 | 4.8% | +0.0537 | -0.35 | 1 |
| Pullback | DE30 | full | 266 | +0.0043 | +0.06 | 40.2% | €940.22 | 30.7% | -0.0677 | +0.67 | 1 |
| Pullback | DE30 | recent | 94 | -0.0898 | -0.73 | 37.2% | €822.75 | 30.7% | -0.1223 | +0.19 | 1 |
| Pullback | US500 | full | 278 | +0.1436 | +1.58 | 39.6% | €1,960.14 | 21.8% | -0.1421 | +2.90 | 0.589 |
| Pullback | US500 | recent | 100 | +0.0955 | +0.63 | 40.0% | €1,157.98 | 17.1% | -0.2251 | +1.85 | 1 |
| Pullback | USTEC | full | 283 | +0.1635 | +1.90 | 43.5% | €2,244.85 | 21.5% | +0.0224 | +1.46 | 1 |
| Pullback | USTEC | recent | 102 | +0.0407 | +0.31 | 42.2% | €1,048.23 | 21.5% | +0.0252 | +0.10 | 1 |
| Pullback | XAUUSD | full | 340 | +0.1623 | +2.16 | 47.4% | €2,650.66 | 26.5% | -0.0062 | +1.76 | 1 |
| Pullback | XAUUSD | recent | 75 | +0.3421 | +2.10 | 52.0% | €1,620.42 | 13.8% | -0.0750 | +2.00 | 1 |
| TickBurst_5m | EURUSD | full | 10772 | -0.4269 | -39.83 | 20.3% | <€0.01 | 100.0% | -0.4284 | +0.13 | 1 |
| TickBurst_5m | EURUSD | recent | 10772 | -0.4269 | -39.83 | 20.3% | <€0.01 | 100.0% | -0.4284 | +0.13 | 1 |
| TickBurst_5m | US500 | full | 12510 | -0.3762 | -37.04 | 23.2% | <€0.01 | 100.0% | -0.3648 | -1.02 | 1 |
| TickBurst_5m | US500 | recent | 12510 | -0.3762 | -37.04 | 23.2% | <€0.01 | 100.0% | -0.3648 | -1.02 | 1 |
| TickBurst_5m | USTEC | full | 8319 | -0.2614 | -15.25 | 25.5% | <€0.01 | 100.0% | -0.2417 | -1.08 | 1 |
| TickBurst_5m | USTEC | recent | 8319 | -0.2614 | -15.25 | 25.5% | <€0.01 | 100.0% | -0.2417 | -1.08 | 1 |
| TickBurst_5m | XAUUSD | full | 9116 | -0.1839 | -11.85 | 28.9% | <€0.01 | 100.0% | -0.1829 | -0.05 | 1 |
| TickBurst_5m | XAUUSD | recent | 9116 | -0.1839 | -11.85 | 28.9% | <€0.01 | 100.0% | -0.1829 | -0.05 | 1 |
| TurtleSoup | DE30 | full | 189 | -0.0034 | -0.04 | 43.4% | €940.87 | 29.3% | +0.0071 | -0.10 | 1 |
| TurtleSoup | DE30 | recent | 53 | +0.0886 | +0.49 | 45.3% | €1,079.26 | 10.5% | -0.1032 | +0.87 | 1 |
| TurtleSoup | EURUSD | full | 285 | +0.0253 | +0.40 | 49.1% | €1,084.24 | 24.2% | -0.1235 | +1.85 | 1 |
| TurtleSoup | EURUSD | recent | 50 | +0.0372 | +0.20 | 44.0% | €1,021.67 | 9.7% | -0.1358 | +0.81 | 1 |
| TurtleSoup | GBPUSD | full | 284 | -0.0220 | -0.34 | 43.7% | €825.48 | 43.1% | +0.0651 | -1.04 | 1 |
| TurtleSoup | GBPUSD | recent | 62 | -0.0313 | -0.27 | 40.3% | €952.01 | 13.8% | +0.1331 | -1.02 | 1 |
| TurtleSoup | US500 | full | 237 | -0.0699 | -0.99 | 37.6% | €679.84 | 43.1% | -0.0636 | -0.08 | 1 |
| TurtleSoup | US500 | recent | 63 | -0.0932 | -0.79 | 42.9% | €879.60 | 30.4% | -0.0868 | -0.05 | 1 |
| TurtleSoup | USDJPY | full | 273 | -0.0480 | -0.78 | 41.0% | €727.18 | 42.5% | -0.0401 | -0.10 | 1 |
| TurtleSoup | USDJPY | recent | 59 | -0.1334 | -1.17 | 37.3% | €846.61 | 19.4% | +0.0110 | -0.91 | 1 |
| TurtleSoup | USTEC | full | 239 | -0.1920 | -2.79 | 34.3% | €378.14 | 64.3% | -0.1740 | -0.21 | 1 |
| TurtleSoup | USTEC | recent | 65 | -0.2989 | -2.87 | 33.8% | €671.18 | 35.0% | -0.3033 | +0.03 | 1 |
| TurtleSoup | XAUUSD | full | 255 | +0.0408 | +0.56 | 45.5% | €1,151.82 | 28.2% | +0.1026 | -0.66 | 1 |
| TurtleSoup | XAUUSD | recent | 47 | +0.2574 | +1.22 | 46.8% | €1,249.43 | 12.3% | +0.3409 | -0.39 | 1 |
| Williams | DE30 | full | 1436 | -0.0061 | -0.39 | 48.1% | €756.07 | 45.8% | -0.0278 | +1.03 | 1 |
| Williams | DE30 | recent | 405 | +0.0059 | +0.20 | 49.9% | €1,020.42 | 21.4% | -0.0137 | +0.52 | 1 |
| Williams | EURUSD | full | 2147 | -0.0185 | -1.40 | 47.5% | €384.60 | 67.4% | -0.0284 | +0.54 | 1 |
| Williams | EURUSD | recent | 426 | -0.0240 | -0.80 | 44.6% | €788.64 | 29.9% | -0.0419 | +0.45 | 1 |
| Williams | GBPUSD | full | 2138 | -0.0170 | -1.28 | 47.5% | €410.71 | 78.1% | -0.0231 | +0.34 | 1 |
| Williams | GBPUSD | recent | 423 | +0.0480 | +1.68 | 50.1% | €1,457.06 | 10.3% | -0.0477 | +2.40 | 1 |
| Williams | US500 | full | 1471 | -0.0271 | -1.68 | 48.3% | €403.13 | 68.8% | -0.0279 | +0.04 | 1 |
| Williams | US500 | recent | 421 | -0.0179 | -0.58 | 47.0% | €831.46 | 34.4% | +0.0014 | -0.46 | 1 |
| Williams | USDJPY | full | 2136 | -0.0650 | -0.91 | 47.8% | <€0.01 | 100.0% | -0.0252 | -0.55 | 1 |
| Williams | USDJPY | recent | 425 | +0.0186 | +0.62 | 52.0% | €1,134.70 | 18.0% | -0.0097 | +0.67 | 1 |
| Williams | USTEC | full | 1488 | -0.0046 | -0.28 | 49.6% | €771.28 | 39.8% | -0.0062 | +0.07 | 1 |
| Williams | USTEC | recent | 430 | -0.0148 | -0.47 | 48.8% | €849.61 | 37.4% | +0.0021 | -0.41 | 1 |
| Williams | XAUUSD | full | 2059 | +0.0391 | +2.84 | 49.4% | €4,259.22 | 23.0% | -0.0133 | +2.79 | 0.776 |
| Williams | XAUUSD | recent | 421 | +0.0858 | +2.87 | 52.3% | €1,994.26 | 10.8% | +0.0385 | +1.13 | 1 |
