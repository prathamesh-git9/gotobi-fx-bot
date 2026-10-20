# Research report: six different intraday hypotheses

**Verdict:** None qualifies as a positive trading edge on the 2022-01-01 to 2026-09-30 holdout. Only US500 to USDJPY had a positive holdout mean; it was tiny, statistically weak, and worse than its matched random-direction control. Gold to AUDUSD was significantly *negative* (two-sided p = 0.0042), including after the six-idea Bonferroni cutoff of 0.00833. Reversing that rule would be a new, untested hypothesis. The EURJPY triangle rule generated zero trades at its fixed threshold.

`RULES.md` was written before strategy returns were computed. It fixes six signals, thresholds, trade times, stops and evaluation. No rule was tuned or selected using holdout results. Thresholds were fixed in advance rather than optimized on the development period; that period is shown for transparency. An implementation correction to the quiet-day eligibility calculation required a full rerun under the same rules. Run `python research.py` to regenerate `results.json`.

## Holdout: 2022-01-01 to 2026-09-30

| Idea | Trades | Pips/trade | t | Win % | EUR 1k final | Max DD % | Random pips/trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. US500 to USDJPY | 543 | 0.32 | 0.29 | 44.8 | 1,040 | 45.0 | 1.06 |
| 2. Gold to AUDUSD | 454 | -2.70 | -2.88 | 39.2 | 286 | 73.4 | -1.68 |
| 3. US500 to next DE30 open | 458 | -4.10 | -1.07 | 43.7 | 682 | 57.6 | -6.90 |
| 4. EURJPY triangle | 0 | NA | NA | NA | 1,000 | 0.0 | NA |
| 5. USDJPY shock reversal | 93 | -7.08 | -2.04 | 26.9 | 590 | 43.6 | 2.19 |
| 6. Quiet-day EURUSD | 223 | -0.92 | -0.79 | 45.3 | 805 | 27.6 | -0.54 |

Two-sided t-test p-values: 1: 0.7690; 2: 0.0042; 3: 0.2857; 4: unavailable; 5: 0.0445; 6: 0.4303. The significance requirement is positive mean and p < 0.00833, plus mean above the random control. None passes.

## Full requested ten years: 2016-10-01 to 2026-09-30

| Idea | Trades | Pips/trade | t | Win % | EUR 1k final | Max DD % | Random pips/trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. US500 to USDJPY | 811 | -0.29 | -0.37 | 44.3 | 744 | 60.0 | 0.19 |
| 2. Gold to AUDUSD | 855 | -2.16 | -3.18 | 41.5 | 150 | 85.9 | -1.16 |
| 3. US500 to next DE30 open | 685 | -4.87 | -1.59 | 43.8 | 511 | 66.7 | -8.47 |
| 4. EURJPY triangle | 0 | NA | NA | NA | 1,000 | 0.0 | NA |
| 5. USDJPY shock reversal | 117 | -6.60 | -2.21 | 29.1 | 538 | 49.6 | 1.15 |
| 6. Quiet-day EURUSD | 478 | -0.94 | -1.19 | 45.6 | 617 | 48.8 | -0.08 |

US500 and DE30 data start in 2019-08, so ideas 1 and 3 cover 2019-08 onward within this requested window. Their earlier years are unavailable, not zero-return years.

## Most recent two years: 2024-10-01 to 2026-09-30

| Idea | Trades | Pips/trade | t | Win % | EUR 1k final | Max DD % | Random pips/trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. US500 to USDJPY | 209 | 0.05 | 0.03 | 45.9 | 974 | 19.1 | -1.48 |
| 2. Gold to AUDUSD | 220 | -3.54 | -3.12 | 37.7 | 461 | 56.1 | -1.94 |
| 3. US500 to next DE30 open | 143 | 10.52 | 1.22 | 51.7 | 1,307 | 13.9 | -12.48 |
| 4. EURJPY triangle | 0 | NA | NA | NA | 1,000 | 0.0 | NA |
| 5. USDJPY shock reversal | 26 | -6.18 | -0.86 | 26.9 | 875 | 14.2 | 3.70 |
| 6. Quiet-day EURUSD | 83 | -0.00 | -0.00 | 50.6 | 993 | 11.2 | -1.29 |

## Development: 2016-10-01 to 2021-12-31

| Idea | Trades | Pips/trade | t | Win % | EUR 1k final | Max DD % | Random pips/trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1. US500 to USDJPY | 268 | -1.55 | -1.70 | 43.3 | 715 | 41.2 | -1.56 |
| 2. Gold to AUDUSD | 401 | -1.54 | -1.57 | 44.1 | 526 | 50.8 | -0.56 |
| 3. US500 to next DE30 open | 227 | -6.41 | -1.28 | 44.1 | 749 | 29.8 | -11.64 |
| 4. EURJPY triangle | 0 | NA | NA | NA | 1,000 | 0.0 | NA |
| 5. USDJPY shock reversal | 24 | -4.74 | -0.84 | 37.5 | 912 | 13.6 | -2.90 |
| 6. Quiet-day EURUSD | 255 | -0.95 | -0.88 | 45.9 | 767 | 32.7 | 0.33 |

US500/DE30 development begins 2019-08. The triangular rule has no t-statistic or win rate because it has zero trades. For zero trades, the unchanged EUR 1,000 balance and 0% drawdown are bookkeeping values, not performance evidence.

## Idea-level verdicts

1. **US equities lead yen:** Holdout +0.32 pip/trade, t = 0.29; random direction +1.06. No evidence that index direction predicts yen after spread. The 45% drawdown is substantial for essentially flat P&L.

2. **Gold leads Australian dollar:** Holdout -2.70 pips/trade, t = -2.88. The proposed direction fails in both development and holdout; the negative result passes the two-sided multiple-test threshold but supports rejection, not an inverse-trade claim.

3. **US close leads Germany:** Holdout -4.10 index points/trade; recent two years +10.52 points/trade but t = 1.22 over 143 trades. The later improvement is exploratory and not enough to overcome the full holdout failure.

4. **Triangular FX delayed adjustment:** Fixed 5 bp residual never occurred at the sampled quotes. No tradable test or inference. Lowering the threshold now would require a fresh holdout.

5. **Yen post-shock reversal:** Holdout -7.08 pips/trade, 27% win rate and 44% drawdown. The proposed reversal direction fails; the random-direction benchmark averaged +2.19 pips on the same times.

6. **Quiet-day FX continuation:** Holdout -0.92 pip/trade, t = -0.79; random direction -0.54. No evidence of a favorable continuation effect.

## Execution and interpretation

- Signals use available minute-bar mid closes; entries and scheduled exits use subsequent bid/ask opens. Longs buy ask and sell bid; shorts sell bid and cover ask. Stops use adverse bid lows/ask highs and adverse opening gaps; the stop has priority. There are no targets. The random benchmark replaces only direction, keeping the same signaled dates, trade window, stop, spread and 2% risk sizing. One seeded coin sequence is descriptive, not a formal randomization distribution.
- Pips mean 0.01 for JPY pairs, 0.0001 for other FX; DE30 is shown in index points. EUR 1,000 paths restart at each reported period, sizing every trade at 2% of then-current equity using the stop distance plus entry spread. Max drawdown is based on end-of-trade equity; adverse excursion within open trades could be greater.
- All holds end the same UTC trading day, so overnight financing/swap is assumed EUR 0. The broker quote spread is included; extra commissions, slippage beyond specified adverse stop gaps, market impact, and financing during an intraday hold are not modeled. These omissions can make practical results worse.
- Student t-tests assume independent trade outcomes. Serial dependence and volatility clustering can make their p-values optimistic. The Bonferroni cutoff controls six idea-level tests only; these data and hypotheses do not establish a deployable edge.
