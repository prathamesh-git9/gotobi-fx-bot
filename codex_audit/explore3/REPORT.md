# Scheduled-flow / calendar edges: round 3

**Verdict: no survivor.** Seven new, preregistered ideas were tested. None cleared the one-sided paired-control test after Bonferroni correction (required adjusted p < 0.05). No per-year pip or EUR 1,000 compounding curve is reported because `RULES.md` reserves those for survivors. The closest observed effects were UK holiday reopening and the UK fiscal-year boundary, but their adjusted p-values were 0.470 and 0.431, respectively; the latter has only four holdout trades.

`RULES.md` was written before any returns were computed. `research.py` implements those rules, and `results.json` contains the full numerical output. Training covered 2016-2021 for FX and 2019-2021 for indices; the untouched judgment period was 2022-01-01 through 2026-09-30. Only the holding time (30, 60 or 120 minutes) was selected on training event-minus-control mean. Every trade used actual bid/ask, minute-bar opens, equal-distance stops and targets, and stop priority when both levels were touched in one bar. The control used the same local clock and weekday one week earlier, with its own momentum signal when applicable. Missing minute sequences and event-contaminated controls were skipped. Returns below are net of observed spread, in units of the fixed stop distance (R). The p-value is from 100,000 seeded paired sign flips; seven tests were Bonferroni-adjusted.

| Idea | Chosen hold | Training pairs; difference R | Holdout pairs | Event mean R | Control mean R | Difference R | Event win % | Net pips / points | One-sided p | Adjusted p | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| US holiday reopening, US500 | 120m | 17; +0.199 | 46 | +0.066 | -0.003 | +0.068 | 58.7 | +90.62 points | 0.348 | 1.000 | Fail; weak control advantage, negative event mean in 2025-26 |
| German holiday reopening, DE30 | 30m | 9; -0.125 | 23 | +0.012 | -0.161 | +0.173 | 39.1 | +27.70 points | 0.155 | 1.000 | Fail; training and holdout evidence insufficient |
| UK holiday reopening, GBPUSD | 120m | 25; +0.603 | 23 | +0.214 | -0.046 | +0.261 | 65.2 | +123.10 pips | 0.067 | 0.470 | Fail; suggestive but does not clear multiplicity |
| Japan holiday reopening, USDJPY | 30m | 39; -0.057 | 39 | -0.122 | -0.074 | -0.049 | 43.6 | -119.40 pips | 0.626 | 1.000 | Fail; negative absolute and relative result |
| Quarterly FX futures expiry proxy, EURUSD | 120m | 23; +0.104 | 17 | +0.009 | +0.181 | -0.172 | 52.9 | +3.70 pips | 0.745 | 1.000 | Fail; ordinary controls did better |
| US estimated-tax settlement, US500 | 120m | 7; -0.092 | 19 | -0.160 | -0.028 | -0.132 | 42.1 | -91.37 points | 0.740 | 1.000 | Fail; negative absolute and relative result |
| UK fiscal-year boundary, GBPUSD | 30m | 4; +0.642 | 4 | +0.498 | -0.472 | +0.970 | 75.0 | +49.80 pips | 0.062 | 0.431 | Fail; only four holdout pairs |

The UK holiday effect was almost flat in 2022-2024 (+0.002 event R per trade) and stronger in 2025-2026 (+0.544), so it does not show a steady regime-independent effect. The US holiday event mean moved from +0.153 R in 2022-2024 to -0.099 R in 2025-2026. The UK fiscal-year result is too sparse to support a conclusion despite positive means in both subperiods.

Calendar dates are **proxies** for tradeable flows: US federal holidays are not identical to exchange closures, the quarterly third-Wednesday rule does not verify each currency-futures contract's last trade, and the tax/fiscal dates are not observed settlement timestamps. The one-week-earlier control may differ in other calendar conditions. The bid/ask bars include spread but no additional slippage or financing. These limitations would weaken an apparent positive finding; here they do not turn any idea into a survivor.
