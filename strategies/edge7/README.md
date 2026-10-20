# Round 7: the European-open drift, opening-gap fills, and a portfolio of what works

This is my half of round 7. Codex ran a broad technical edge hunt independently in
[codex_audit/edge_hunt](../../codex_audit/edge_hunt/REPORT.md).

The rules were fixed before running; see the [lab7.py](lab7.py) docstring. The data is real Exness bid/ask minute
bars, with indices from Aug 2019.

## O: the overnight drift at the European open

Boyarchenko, Larsen & Whelan, *The Overnight Drift*, Review of Financial Studies 2023 (NY Fed Staff Report 917).
They found US index futures earn their biggest returns 02:00–03:00 New York time, averaging +1.48 bp a day over
1998–2020, and more after sell-offs.

| Buy 02:00, sell 03:00 NY | US500 | USTEC | US30 |
|---|---:|---:|---:|
| Every day, 2019–26 | −0.043R | −0.037R | −0.031R |
| Every day, last 2 yrs | −0.003R | +0.008R | −0.001R |
| After a down US session, last 2 yrs | −0.008R | −0.007R | −0.006R |
| After a down last half-hour, last 2 yrs | +0.006R | +0.014R | +0.006R |

R here is relative to a 0.5% catastrophe stop, so 1 bp = 0.02R.

**Fail.** Before Q4 2024 the 3–4 bp night spread was more than twice the whole effect. At today's 0.4–0.9 bp
spread it is breakeven: the drift is still there before costs, worth about one spread.

## G: opening-gap fill

Rule: fade gaps of 0.15–0.60% toward the previous close, 1:1 stop, out by the close.

| | US500 | USTEC | US30 | DAX |
|---|---:|---:|---:|---:|
| 2019–26 | −0.06R | −0.04R | −0.03R | −0.13R |
| Last 2 yrs | −0.07R | −0.03R | −0.01R | +0.03R |

**Fail.** Small gaps do fill often (win rates 43–49% at 1:1), but not often enough to pay the spread.

## P: a portfolio of the four things that work

Each strategy is a separate sleeve, compounded daily, Sep 2019 – Sep 2026:
- gotobi USDJPY bot at 6% risk: its own replay trade list,
  [gotobi_bot_trades_2016_2026.csv](gotobi_bot_trades_2016_2026.csv);
- gotobi long EURJPY at 3%;
- GBPUSD into the month-end fix at 3%;
- NASDAQ noise-area momentum (round 6) at half the paper's size, at today's spread.

| | Correlation of daily returns |
|---|---|
| gotobi USDJPY vs EURJPY | 0.19 |
| every other pair | −0.03 … 0.07 |

| EUR 1,000 | Since Sep 2019 | Max drop | Sharpe | Last 2 yrs |
|---|---:|---:|---:|---:|
| gotobi bot alone (6%) | EUR 19,040 (+51.6%/yr) | 41.0% | 1.75 | +95.1%/yr |
| all four, scaled to the bot's 2019–21 risk (×0.69) | EUR 21,485 (+54.2%/yr) | **33.1%** | **2.06** | +75.8%/yr |
| all four, unscaled | EUR 78,413 (+85.2%/yr) | 44.9% | 2.06 | +123.8%/yr |

**Read it this way:**
- At the same risk, adding the three small, unrelated edges keeps the return and cuts the worst drop from 41% to
  33%.
- In a year when gotobi alone does unusually well, as in 2025–26, the mix earns less.
- These are backtests: real fills, slippage and the NASDAQ "today's spread" assumption can only make them worse.
- The EURJPY and GBPUSD rules came out of a search, though both held up on unseen 2006–2015 data.

```
python strategies/edge7/lab7.py [O G P]
```
