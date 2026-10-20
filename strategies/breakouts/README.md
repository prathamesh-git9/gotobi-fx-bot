# Round 6: breakouts, support/resistance, round numbers and order flow, the published versions

This is my half of round 6. Codex worked on the same question independently in
[codex_audit/smc_research](../../codex_audit/smc_research/REPORT.md), without seeing this code.

The rules are fixed in the [lab6.py](lab6.py) docstring, taken from each paper as literally as our data allows.
Everything runs on real Exness bid/ask minute bars:
- indices from Aug 2019,
- FX and gold from 2016.

## What the research says (sources)

**Who actually makes money:**
- Brazilian futures day traders who kept at it for 300+ days: 97% lost money, and about 0.4% earned more than a
  bank teller. Chague, De-Losso & Giovannetti, "Day Trading for a Living?" (FGV / SSRN 2019).
- Taiwan day traders lose in aggregate; a small minority is persistently profitable. Barber, Lee, Liu & Odean,
  "The Cross-Section of Speculator Skill", Journal of Financial Markets 2014.
- Prop-firm data (FPFX Tech, about 100,000 traders across 10 firms): about 7% ever received a payout.

**Stop hunts are real, but they push price onward, not back.** Carol Osler (NY Fed Staff Reports 125, 150;
J. Finance 2003; JIMF 2005) found:
- stop-loss orders cluster just beyond round numbers;
- when they fire, the move speeds up and continues ("price cascades");
- take-profit orders sit exactly on round numbers.

That is the opposite of SMC's "sweep then reverse".

**Order flow:**
- Order-flow imbalance in the exchange's order book explains price changes over seconds. Cont, Kukanov & Stoikov,
  "The Price Impact of Order Book Events", J. Financial Econometrics 2014.
- An MT5 CFD feed is the broker's own quotes. It has no exchange volume, no buyer/seller (aggressor) side and no
  depth, so footprint/delta tools on CFD data only show quote changes.

**Published intraday breakout strategies:**
- Opening-range breakout: Zarattini & Aziz 2023, SSRN 4416622. An independent replication on index CFDs found
  "gross reproduced, net zero".
- "Beat the Market" noise-area momentum: Zarattini, Aziz & Barbon 2024. They report a Sharpe of 1.33 on SPY,
  2007–2024.
- Market intraday momentum: Gao, Han, Li & Zhou, JFE 2018. Already tested here as `src/close_mom*.py`; dead on US
  indices 2024–26.

## Results

### B1: opening-range breakout

Rule: trade in the direction of the first 5-minute candle, 10R target. Per trade, after the real spread, Aug 2019
to Sep 2026:

| | NASDAQ | S&P 500 | Dow | DAX |
|---|---:|---:|---:|---:|
| Net, real spread | 0.00R | −0.16R | −0.10R | −0.18R |
| Gross, no spread ([lab6_gross.py](lab6_gross.py)) | **+0.15R (t 2.7)** | +0.11R | +0.02R | +0.10R |

- The paper's +0.13R and 24% hit rate reproduce gross on NASDAQ, but the spread eats all of it.
- The "in play" filter (busy days, by tick count) and the order-flow imbalance filter do not help.
- The imbalance proxy is not stable: its threshold set in 2019–21 almost never triggers after 2024.

### B2: "Beat the Market" noise-area momentum

Sizing follows the paper: a 2% daily-volatility target, at most 4x.

| | Since Sep 2019 | 2019–21 | 2022–26 | Last 2 yrs |
|---|---:|---:|---:|---:|
| NASDAQ, gross | +15.9%/yr, Sharpe 1.17, t 3.1 | +11.3% | +18.2% | +7.4% |
| NASDAQ, **today's spread** | **+11.9%/yr, Sharpe 0.91, t 2.4** | +7.3% | +14.3% | +3.5% |
| NASDAQ, real spread | +3.6%/yr | −6.2% | +8.8% | +3.9% |
| S&P 500, gross | +15.9%/yr, Sharpe 1.06, t 2.8 | +25.3% | +11.6% | −0.8% |
| S&P 500, today's spread | +9.9%/yr, t 1.9 | +19.3% | +5.6% | −6.7% |
| S&P 500, real spread | −1.4%/yr | +1.3% | −2.8% | −6.5% |

- Exness cut US index spreads from 3–4 bp to about 0.9 bp in Q4 2024, and to 0.4–0.65 bp in Q3 2026. The
  "today's spread" rows ([lab6_today_cost.py](lab6_today_cost.py)) charge that level over the whole history.
- The intraday long benchmark (09:30–15:58 every day, same sizing) loses, so the strategy is not just market
  exposure.
- **Verdict: the strongest candidate of round 6, but not proven.**
  - The edge is real gross on both indices.
  - At today's NASDAQ spread it is positive in both halves (t 2.4, below the 2.8 Bonferroni bar).
  - It has been weak since the paper was published in 2024: +3.5%/yr on NASDAQ, negative on the S&P.
  - Worth a demo forward test on NASDAQ only.

### B4: round numbers (Osler)

Rule: after price crosses a round level (EURUSD/GBPUSD x.x000 / x.x050, USDJPY xx.00 / xx.50), follow it for 30
minutes. The placebo is the same rule at levels 23 or 37 pips away.

Round-number crosses lose LESS than placebo crosses in all three pairs, consistent with Osler's stop-loss cascades.

| | Round | Placebo +23 | Placebo +37 |
|---|---:|---:|---:|
| EURUSD | −1.19 pips | −1.27 | −1.76 |
| GBPUSD | −1.31 pips | −1.96 | −1.58 |
| USDJPY | −0.68 pips | −1.45 | −1.44 |

- The effect is real but under 1 pip, well below the cost of a trade, so nothing is tradable.
- Fading a near-touch of a round number (treating it as support/resistance) is no better than fading arbitrary
  levels, and all of those lose.

### B5: prior-session high/low breakout

Rule: follow the break, stop 0.25 × average daily range, target 2R.

| | NASDAQ | S&P 500 | DAX | Gold |
|---|---:|---:|---:|---:|
| Full period | +0.03R (t 0.6) | −0.05R | −0.06R | −0.08R |
| Last 2 yrs | +0.20R (t 1.9) | +0.13R | −0.02R | +0.02R |

None passes: only the last two years are positive, and none is significant.

```
python strategies/breakouts/lab6.py [B1 B2 B4 B5]     # real spreads (~45 min)
python strategies/breakouts/lab6_gross.py B1 B2      # no spread
python strategies/breakouts/lab6_today_cost.py B2    # today's spread over the whole history
```
