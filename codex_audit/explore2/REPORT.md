# Scheduled-flow study, round 2

**Verdict: no survivor; none of these rules is ready to automate.** The closest result is long USD/JPY on BoJ decision mornings (holdout one-sided p = 0.0177; matched-control p = 0.0300). Both miss the predeclared Bonferroni threshold of **0.00833**, and its 2006–2015 check contains only eight 2015 events. The strong selection-period GBP/USD weekend-gap result (t = 3.56) falls to t = 0.38 on the untouched period.

The rules and scoring method were written in [RULES.md](RULES.md) before return calculations. [research.py](research.py) is the reproducible code; [results.json](results.json) contains every candidate's train and holdout statistics. Selection used 2016–2021, or 2019–2021 for the indices; the sole final evaluation used 2022–2026-09-30. USD/JPY Japan rules also received an untouched 2006–2015 check with *modeled* Exness ask spreads. No rule was modified in response to holdout returns.

## Selected rules: holdout evidence

One-sided t tests ask whether the preselected trade's mean return is positive. The control test uses the event return minus its paired ordinary-day return. Both tests must have p < 0.00833 and at least 20 holdout trades; Japan ideas also require positive older-period mean. Returns are net of observed bid/ask spread. Index returns additionally subtract estimated 6% yearly CFD financing for actual holding hours. `t` and `p` are conventional trade-level t statistics and are optimistic if trades are dependent.

| Idea and selected rule | Train n, t | Holdout n | Mean net/trade | Holdout t, p | Event minus control t, p | Result |
|---|---:|---:|---:|---:|---:|---|
| Pre-FOMC: long XAU/USD, prior day 14:00 NY to 15 min before release | 47, 1.31 | 38 | 0.142% | 0.96, 0.1710 | 0.67, 0.2533 | Fail |
| Pre-NYSE holiday: long US500 15:00–16:00 NY | 6, 1.62 | 16 | −0.068% | −1.51, 0.9237 | −0.93, 0.8169 | Fail; under 20 trades |
| Toshin: long USD/JPY, first Japanese business day, 09:00–10:00 Tokyo | 69, −0.98 | 56 | −0.037% | −1.48, 0.9274 | −1.58, 0.9401 | Fail |
| Japan half-year reversal: long USD/JPY, first five business days of April/October, 09:00–17:00 Tokyo | 59, −0.13 | 45 | 0.055% | 1.52, 0.0682 | 1.61, 0.0573 | Fail |
| Weekend gap: follow GBP/USD gap, enter one hour after Sunday open, exit 12 hours later | 204, 3.56 | 194 | 0.008% | 0.38, 0.3515 | 0.70, 0.2416 | Fail |
| BoJ day: long USD/JPY, 08:00–11:00 Tokyo | 49, 0.13 | 37 | 0.072% | 2.19, 0.0177 | 1.94, 0.0300 | Fail |

### Holdout totals by calendar year

FX values are pips (10,000 per price unit for EUR/USD and GBP/USD; 100 for USD/JPY). Gold and indices are price points per one unit. These are summed executable bid/ask trade outcomes, **not** returns on a fixed capital account. A dash means no valid paired trades. 2026 ends September 30.

| Selected rule | 2022 | 2023 | 2024 | 2025 | 2026 YTD |
|---|---:|---:|---:|---:|---:|
| XAU/USD pre-FOMC, gold points | −27.63 | 49.49 | 82.01 | −63.04 | 129.46 |
| US500 pre-holiday, index points | — | −0.07 | −11.65 | −45.18 | −5.79 |
| USD/JPY toshin, pips | −0.3 | −26.3 | −61.9 | −88.3 | −144.4 |
| USD/JPY reversal, pips | 216.2 | 122.4 | −17.5 | −70.1 | 76.7 |
| GBP/USD gap follow, pips | −96.7 | 316.5 | 75.4 | 239.5 | −365.0 |
| USD/JPY BoJ day, pips | 162.6 | 52.8 | −20.1 | 50.9 | 140.0 |

### Older USD/JPY check, 2006–2015

| Selected Japan rule | n | Mean net/trade | t, one-sided p | Annual pips, 2006 through 2015 |
|---|---:|---:|---:|---|
| Toshin, first day | 118 | 0.009% | 0.61, 0.2723 | 71.2, −6.4, 41.2, −45.8, 13.2, 90.2, −55.3, −18.1, 5.0, 6.0 |
| April/October reversal | 100 | 0.006% | 0.13, 0.4473 | −35.0, 133.0, 177.0, −37.0, −94.0, −66.0, 17.7, 38.1, −55.5, 28.2 |
| BoJ day | 8 | 0.005% | 0.20, 0.4221 | 2015: 4.8; calendar has no 2006–2014 BoJ dates |

The older check offers no persuasive support. Its ask prices are modeled from bid quotes, so execution costs are less certain than in the Exness data.

## All variants considered on the selection period

Each cell is `selection n / selection t → holdout n / holdout t`. The rule in bold was chosen solely by the largest selection t in its idea family. The holdout figures for unselected variants are descriptive and were **not** used to replace a failed winner. The precise p-values, mean returns and yearly totals for every variant are in `results.json`.

| Idea | Candidate | Train → holdout |
|---|---|---|
| FOMC | EUR/USD | 47 / 0.87 → 38 / 0.25 |
| FOMC | USD/JPY | 47 / −0.35 → 38 / −1.71 |
| FOMC | **XAU/USD** | 47 / 1.31 → 38 / 0.96 |
| FOMC | US500 | 19 / 0.69 → 38 / 1.82 |
| FOMC | US30 | 19 / 0.39 → 38 / 1.27 |
| FOMC | USTEC | 19 / 0.95 → 38 / 2.10 |
| Holiday | 12:00 entry | 6 / 0.18 → 16 / −1.39 |
| Holiday | 14:00 entry | 6 / −0.30 → 16 / −1.23 |
| Holiday | **15:00 entry** | 6 / 1.62 → 16 / −1.51 |
| Toshin | **first 1 business day** | 69 / −0.98 → 56 / −1.48 |
| Toshin | first 2 business days | 141 / −1.27 → 112 / −0.75 |
| Toshin | first 3 business days | 212 / −2.44 → 169 / −0.46 |
| Repatriation | short last 5 March/September business days | 55 / −1.29 → 50 / 0.66 |
| Repatriation | short last 10 March/September business days | 115 / −0.93 → 100 / −0.92 |
| Repatriation | **long first 5 April/October business days** | 59 / −0.13 → 45 / 1.52 |
| Weekend gap | EUR/USD fade 4h | 203 / −2.89 → 193 / −1.65 |
| Weekend gap | EUR/USD fade 12h | 203 / −1.91 → 193 / −2.09 |
| Weekend gap | EUR/USD follow 4h | 203 / −0.07 → 193 / −0.74 |
| Weekend gap | EUR/USD follow 12h | 203 / 0.22 → 193 / 0.90 |
| Weekend gap | GBP/USD fade 4h | 204 / −4.23 → 194 / −1.50 |
| Weekend gap | GBP/USD fade 12h | 204 / −4.84 → 194 / −1.55 |
| Weekend gap | GBP/USD follow 4h | 204 / 1.19 → 194 / 0.05 |
| Weekend gap | **GBP/USD follow 12h** | 204 / 3.56 → 194 / 0.38 |
| Weekend gap | USD/JPY fade 4h | 165 / −1.20 → 157 / −1.27 |
| Weekend gap | USD/JPY fade 12h | 165 / −1.37 → 157 / −1.65 |
| Weekend gap | USD/JPY follow 4h | 165 / −0.63 → 157 / 0.25 |
| Weekend gap | USD/JPY follow 12h | 165 / −0.03 → 157 / 1.06 |
| Weekend gap | XAU/USD fade 4h | 196 / −0.74 → 222 / −1.23 |
| Weekend gap | XAU/USD fade 12h | 196 / −0.64 → 222 / −2.17 |
| Weekend gap | XAU/USD follow 4h | 196 / −1.03 → 222 / 0.72 |
| Weekend gap | XAU/USD follow 12h | 196 / −0.27 → 222 / 1.82 |
| BoJ | **long USD/JPY 08:00–11:00** | 49 / 0.13 → 37 / 2.19 |

## Execution and limits

- Trades enter and exit at one-minute bar **opens**: longs buy ask and sell bid; shorts sell bid and buy ask. Both endpoints must exist within five minutes of the specified time. A paired control must also be executable. No stop or target is used, so the stop-first rule when both are touched does not arise.
- The holiday test has only six valid selection trades and 16 holdout trades after the quote and paired-control requirements. It cannot justify choosing a window confidently. Some apparent holiday closures may have different CFD hours.
- Overnight index positions pay an estimated 6% annual financing on notional. Actual broker charges may differ. Overnight FX and gold swaps, slippage, commissions, order rejection, and market impact were not modeled; these would usually worsen executable results. Weekend reopening spreads and thin liquidity are a particular concern for the gap idea.
- A BoJ *decision day* is known in advance, but the decision release time is absent from this calendar; the 08:00–11:00 window cannot be guaranteed to end before an actual decision. This limits the interpretation of the BoJ result.
- The 2% risk per trade compounding exercise was predeclared only for survivors. **There are zero survivors**, so no final balance, drawdown, trade count, or worst-year compounding result is claimed. With no stop, the proposed 1%-of-price risk unit is a sizing convention rather than a maximum loss.
