# Four-rule secondary study

The frozen definitions and reproducible code for this separate run are [RULES_4.md](RULES_4.md) and [research_4.py](research_4.py); machine-readable output is [results_4.json](results_4.json). The root REPORT.md covers the primary eight-rule study. This four-rule run was completed on the same feed before the primary eight-rule script replaced the shared root files.

**Verdict:** None of these four precise prior-day, channel, or BOS/FVG variants made money on the 2022–2026 holdout after the recorded retail spread. All holdout mean R values are negative, all Bonferroni-adjusted one-sided p values for *positive* expectancy are 1.00, and none merits a live-capital forward test. A demo forward test is useful only to audit execution assumptions or test a genuinely new prespecified rule.

Numbers below pool chronological trades across XAUUSDm, USTECm, US500m, EURUSDm, GBPUSDm. Each window restarts with €1,000. `DD` is maximum percentage peak-to-trough drawdown. `Random` is mean R from a matched entry with seeded random direction. The full window begins 2016-10-01 for gold/FX and 2019-08 for indices. USTEC ends 2026-09-29 23:59 UTC; the others reach 2026-09-30 23:59 UTC.

| Rule | Window | Trades | Avg R | t | Win % | Final € | DD % | Random R | Beats random? |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| PD-break | Full | 4,670 | -0.163 | -8.41 | 28.7 | <0.01 | 100.0 | -0.163 | Yes, trivially |
| PD-break | 2024-10 onward | 1,340 | -0.144 | -3.94 | 29.1 | 12.90 | 98.7 | -0.162 | Yes |
| PD-break | Holdout | 2,824 | -0.136 | -5.39 | 29.6 | 0.17 | 100.0 | -0.153 | Yes |
| PD-retest | Full | 2,727 | -0.187 | -7.53 | 28.5 | 0.01 | 100.0 | -0.166 | No |
| PD-retest | 2024-10 onward | 744 | -0.194 | -4.06 | 27.8 | 43.21 | 96.2 | -0.157 | No |
| PD-retest | Holdout | 1,617 | -0.211 | -6.58 | 27.5 | 0.64 | 100.0 | -0.125 | No |
| Channel-break | Full | 24,235 | -0.183 | -21.60 | 27.8 | <0.01 | 100.0 | -0.184 | Yes, trivially |
| Channel-break | 2024-10 onward | 7,360 | -0.153 | -9.80 | 28.7 | <0.01 | 100.0 | -0.154 | Yes, trivially |
| Channel-break | Holdout | 14,860 | -0.173 | -15.92 | 28.1 | <0.01 | 100.0 | -0.172 | No |
| BOS-FVG-retest | Full | 1,424 | -0.164 | -4.73 | 29.1 | 5.64 | 99.5 | -0.143 | No |
| BOS-FVG-retest | 2024-10 onward | 433 | -0.169 | -2.65 | 28.4 | 198.93 | 80.9 | -0.201 | Yes |
| BOS-FVG-retest | Holdout | 889 | -0.169 | -3.82 | 28.7 | 36.24 | 96.4 | -0.164 | No |

The 2R target needs a win rate comfortably above one third when losers are near -1R. Observed win rates are below 30%. The few positive comparisons to random direction are not evidence of profitability because both sides lose. The random series deliberately evaluates every real entry, so its hypothetical trades can overlap. The compounded random account is therefore not a feasible one-position portfolio. Trade-level t tests assume independent observations and can overstate precision amid clustered signals and shared market shocks. Fractional CFD sizing, no added slippage, and no margin cap are optimistic; these caveats cannot explain away the negative measured expectancy.
