# SMC, breakouts and order flow on the Exness Standard feed

Completed 20 October 2026. [Research and sources](RESEARCH.md) · [Frozen rules and audit note](RULES.md) · [Executable backtest](research.py) · [Full machine-readable results](results.json) · [Trade log](trades.csv).

## Verdict

**None of the eight tested rules establishes a durable, tradeable edge on these CFDs.** On the 2022-01-01–2026-09-30 holdout, only the NASDAQ opening-range breakout (R3) and the S&P noise-band strategy (R5) have positive average R, at +0.0592R and +0.0006R respectively. Neither beats its same-entry random-direction control convincingly; both one-sided positive-mean p values are 1.0 after Bonferroni correction across eight rules. The NASDAQ ORB has a 90.3% compounded drawdown at the required 2% initial-stop risk even in its positive holdout. The other six rules lose on average. An audited small minority of day traders and some regulated trend-following funds do make money; these results offer no evidence that their profits come from SMC labels, a CFD quote-delta proxy, or the tested breakouts.

The stock and SPY papers are **not exact replications** here. R3/R4 replace US stocks or QQQ with a USTEC CFD, stop entries with next-open entries, and stock share volume with broker quote count. R5 replaces SPY exchange VWAP with quote-count-weighted CFD price. R6 turns a published predictive regression into a signed last-half-hour trade. We follow the papers' observable signal ideas but cannot infer that their published stock/ETF results have failed merely because these CFD adaptations fail.

## How to read the tables

Each table starts a *new* €1,000 account at the start of its window, compounds 2% of current balance per trade per initial-stop R, and reports the maximum peak-to-trough drawdown. `Full` is 2016-10-01–2026-09-30 for FX/gold and begins 2019-08 for indices; mixed R1/R2 use each symbol's available start. `Recent` is 2024-10-01–2026-09-30. Figures use actual ask entry/bid exit for longs and bid entry/ask exit for shorts. No overnight holds or swap. `t` is a trade-level t statistic for mean R versus zero, not a cluster-robust proof. A printed drawdown of ~100% is a near-total loss, not necessarily an exact zero balance. Cross-symbol entries are prioritized mechanically and no rule has overlapping trades.

### R1 — sweep, displacement, FVG retest

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 894 | −0.1053 | −2.63 | 34.9% | €117.91 | 91.2% |
| Holdout | 486 | −0.0872 | −1.58 | 35.2% | €371.43 | 74.7% |
| Recent | 196 | +0.0154 | +0.17 | 38.3% | €998.26 | 39.2% |

**Verdict:** The FVG-confirmed sweep is still a loser over the full and holdout windows. Recent mean R is near zero and the account still contracts. This does not support a liquidity-grab edge. Gold and the indices are particularly weak; EURUSD has a positive holdout subseries, which is post-hoc and too small to promote as a new rule.

### R2 — support/resistance break and retest

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 13,908 | −0.2361 | −21.89 | 26.5% | <€0.01 | ~100% |
| Holdout | 7,372 | −0.2087 | −13.91 | 27.5% | <€0.01 | ~100% |
| Recent | 3,056 | −0.1973 | −8.41 | 27.8% | €0.0020 | ~100% |

**Verdict:** Broad failure across all five symbols. A visible break/retest can be a valid chart description without being an executable advantage at retail spread.

### R3 — NASDAQ 5-minute opening-range breakout

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 1,561 | −0.0234 | −0.35 | 17.4% | €70.13 | 98.2% |
| Holdout | 1,047 | +0.0592 | +0.69 | 18.2% | €811.18 | 90.3% |
| Recent | 445 | +0.1019 | +0.83 | 22.5% | €1,447.06 | 63.8% |

**Verdict:** The recent improvement is the most interesting *research lead*, but it is statistically weak and highly exposed to a few large winners. Its holdout random-direction control averages +0.0446R on the same entries, versus +0.0592R for the rule. Paired t=0.15. The full-period capital loss and the large recent drawdown rule out a funded 2%-risk CFD forward test.

### R4 — NASDAQ ORB with relative tick count ≥ 1

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 757 | −0.0791 | −0.79 | 13.7% | €109.28 | 93.2% |
| Holdout | 516 | −0.0425 | −0.34 | 14.5% | €313.20 | 87.6% |
| Recent | 216 | −0.0703 | −0.38 | 16.7% | €557.40 | 61.5% |

**Verdict:** Filtering one index CFD by quote-count relative volume worsens R3's holdout mean. This cannot refute the published *top 20 stocks in play* result because a single index has no cross-sectional stock selection or real share volume.

### R5 — S&P noise bands and quote-weighted VWAP exit

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 1,586 | +0.0007 | +0.08 | 37.6% | €983.46 | 17.4% |
| Holdout | 1,109 | +0.0006 | +0.06 | 37.2% | €987.44 | 17.4% |
| Recent | 451 | −0.0055 | −0.32 | 38.4% | €940.11 | 17.4% |

**Verdict:** Essentially flat in R, slightly down after compounding. The holdout random-direction control averages −0.0155R, but paired t=1.41 and Bonferroni p=0.638. Broker quote-count VWAP and an added ATR catastrophe stop limit comparability with SPY ETF paper returns.

### R6 — first half-hour sign, trade final half-hour

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 1,756 | −0.0277 | −6.62 | 43.2% | €373.67 | 63.7% |
| Holdout | 1,179 | −0.0170 | −3.50 | 45.7% | €665.21 | 35.1% |
| Recent | 494 | −0.0070 | −1.02 | 46.6% | €931.30 | 9.6% |

**Verdict:** A published SPY *predictive relationship* does not yield positive net R through this fixed CFD sign trade. The signal itself is smaller than spread and quote uncertainty at this execution horizon.

### R7 — FX round-number crossing continuation

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 26,281 | −0.1016 | −17.99 | 39.8% | <€0.01 | ~100% |
| Holdout | 13,089 | −0.0805 | −9.61 | 41.0% | <€0.01 | ~100% |
| Recent | 5,167 | −0.0857 | −6.91 | 42.1% | €0.06 | ~100% |

**Verdict:** Real round levels lose, although less than the shifted-grid placebo on holdout (−0.0805R vs −0.0889R). The placebo's different signal times prevent that small difference from proving a causal round-number effect. A faster post-cross move at the dealer's execution price cannot be inferred from M5 CFD quotes.

### R8 — FX round-number approach fade

| Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Full | 3,635 | −0.0978 | −5.65 | 38.5% | €0.37 | ~100% |
| Holdout | 1,991 | −0.0998 | −4.16 | 38.3% | €11.89 | 98.9% |
| Recent | 678 | −0.1020 | −2.56 | 38.9% | €216.56 | 81.6% |

**Verdict:** The fade loses. Holdout placebo is virtually the same at −0.1003R. Actual conditional take-profit orders are unavailable in this feed.

## Random directions, multiplicity and the papers' mechanisms

The random control keeps each executed signal's entry time and initial stop distance and draws a seeded long/short direction. Paired R differences use the same time and exit rule. This tests whether the chart condition supplies useful **direction**, not whether entry timing alone is special. The control is allowed to exit at a different time, so its paired trades are comparisons, not a second simultaneously executable portfolio.

| Rule | Holdout rule R | Same-entry random R | Paired t | Bonferroni p, rule > random |
|---|---:|---:|---:|---:|
| R1 | −0.0872 | −0.0357 | −0.73 | 1.000 |
| R2 | −0.2087 | −0.2164 | +0.43 | 1.000 |
| R3 | +0.0592 | +0.0446 | +0.15 | 1.000 |
| R4 | −0.0425 | −0.2373 | +1.52 | 0.519 |
| R5 | +0.0006 | −0.0155 | +1.41 | 0.638 |
| R6 | −0.0170 | −0.0237 | +1.02 | 1.000 |
| R7 | −0.0805 | −0.0932 | +1.22 | 0.884 |
| R8 | −0.0998 | −0.0652 | −1.16 | 1.000 |

The 15-minute **price-only** Osler diagnostics, using all qualifying signals before one-position filtering, show crossing-direction continuation on 48.77% of 64,488 round-level events versus 48.22% of 69,138 shifted-grid events. Mean signed moves are −0.00129 versus −0.00252 grid units. At approach-fade signals, 48.53% of 3,944 round events move away from the level versus 46.67% of 3,923 placebos; mean signed moves are +0.00253 versus −0.01283 grid units. These tiny quote effects are consistent with at most a modest round-level difference and do not pay the spread in R7/R8. They do not test actual stop orders; serially repeated events make naive event p values misleading.

## CFD quote activity is not exchange order flow

On holdout, the R2 break/retest is −0.2087R unfiltered, −0.2094R with matching `up−dn` quote direction, −0.1953R with above-median quote count, and −0.1972R with both. R3 ORB is +0.0592R unfiltered, +0.0646R with matching quote direction, but −0.0425R under the first-five-minute relative tick-count filter (R4). R4 improves to −0.0088R when quote direction agrees, still negative. These subsets are exploratory after viewing the holdout and are **not** additional validated rules. No footprint, executed-volume delta, cumulative delta, or order-book imbalance can be reconstructed from broker quote counts. The short-horizon order-flow-imbalance paper in [RESEARCH.md](RESEARCH.md) offers a reason to examine real futures data, not grounds to purchase a large feed or place a CFD trade now.

## Audit limits and next step

- Rules were written before computing returns and no threshold was selected from 2022–2026. During the first holdout inspection, two implementation defects were found and corrected: missing bars could defer a scheduled exit; and pooling symbols allowed simultaneous trades. **The holdout was inspected during corrections and is no longer a pristine one-look test.** This weakens every inferential claim, even though neither change was chosen to raise returns.
- The bid/ask bars pay the observed Standard-feed spread. Intrabar stop and target collisions go to the stop, and gaps through stops fill at the worse next open. M5/M15 bars cannot recover real trade order, adverse slippage, rejects, latency, CFD financing outside the day, or changing contract/margin terms. Those omissions tend to make profitability look better. The supplied USTEC file ends 2026-09-29; other included symbols reach 2026-09-30.
- Trades are sized to a constant *nominal* 2% initial-stop risk without a leverage cap. Rare stop gaps can exceed 2%; tiny stops could require unavailable leverage. € balances are a required stress illustration, **not feasible account forecasts**. Rule accounts are separate; simultaneously running eight rules at 2% each is not evaluated.
- The t tests treat sequential trades as independent and use a one-sided positive-mean and rule-minus-random test, Bonferroni ×8. Autocorrelation, shared market days, and the inspected holdout weaken their interpretation. None passes even these lenient positive-mean tests.

**Forward test:** No funded CFD forward test is justified by these results. The one candidate for further *research* is R3 in actual NQ or a liquid Nasdaq ETF, with its current definition fixed, realistic commission/slippage/margin, and an untouched future period. R5 could be revisited only with genuine SPY volume/VWAP; the current CFD proxy is flat. Buy a short sample of [CME Time & Sales and depth](https://www.cmegroup.com/datamine.html) only if a precise aggressor/depth hypothesis is specified, then check whether it improves R3 beyond price, costs and random-direction controls in a fresh forward sample. These are proposals for new independent studies, not rescue parameter searches on this holdout.
