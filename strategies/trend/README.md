# Round 9: long-horizon edges that need swap-free financing

## Why this round

The ~200 short-term ideas in this repo failed after costs; only scheduled flows work. Two long-documented edges
failed here earlier only because of overnight CFD financing:
- trend following (time-series momentum);
- the overnight anomaly.

Exness says Standard accounts are **swap-free by default** on EURUSD, GBPUSD, USDJPY, XAUUSD and all indices
(Codex's sources: [codex_audit/edge_hunt](../../codex_audit/edge_hunt/REPORT.md), section E). The catch: status
depends on trading activity, and "persistent large overnight positions" can lose it. Codex studies trend following
independently in [codex_audit/trend_swapfree](../../codex_audit/trend_swapfree/REPORT.md).

## Trend following ([tsmom.py](tsmom.py), daily Yahoo data 2006–2026)

Rule:
- signal = the average of the 1-, 3- and 12-month trend directions;
- each market sized to a 12% yearly portfolio volatility;
- weekly trading, paying the spread.

| EUR 1,000 | 2006–2015 | 2016–2026 | Last 10 yrs | Last 2 yrs | 2026 |
|---|---:|---:|---:|---:|---:|
| 8 swap-free markets, zero swap | +4.2%/yr (Sharpe 0.34) | +2.7%/yr (0.21) | EUR 1,464 | EUR 1,065 | EUR 940 |
| same, 3%/yr financing | −2.0%/yr | −8.0%/yr | EUR 480 | EUR 854 | EUR 862 |
| 13 markets (+ other FX, silver), zero swap | +5.2%/yr | −1.0%/yr | EUR 1,045 | EUR 1,021 | EUR 928 |
| holding the 8 markets long, same risk, zero swap | +7.9%/yr | +19.2%/yr (0.80) | EUR 6,695 | EUR 1,637 | EUR 1,073 |

**Verdict:** trend following is weak here, even with zero swap. That matches the industry's post-2015 "trend
drought". Simply holding the markets did far better, but that is market growth (beta), not a trading edge.

## The overnight anomaly ([overnight.py](overnight.py), Exness minute bid/ask, Aug 2019 – Sep 2026)

Rule: buy at 15:58 New York and sell at 09:35 the next morning, every trading day. For comparison, the opposite: own
the index only during the day.

| Per year (EUR 1,000 at 1x notional) | Before costs | Real spread, zero swap | + swap estimate | Last 2 yrs, zero swap | 2026, zero swap |
|---|---:|---:|---:|---:|---:|
| S&P 500 overnight | +12.3% (Sharpe 1.08, t 2.85) | +4.0% | −1.1% | +6.2% | +4.2% |
| NASDAQ overnight | +15.4% (1.11, t 2.92) | **+7.2%** (Sharpe 0.57) | +2.0% | **+8.7%** | +6.7% |
| Dow overnight | +11.8% (1.05, t 2.77) | +6.4% (0.61) | +1.2% | +6.4% | +10.9% |
| S&P 500 intraday (09:35–15:58) | – | −4.0% | – | +3.1% | +1.3% |

- The swap estimate is (3-month T-bill + 2.5%)/360 a night, triple on Fridays.
- The round-trip spread paid fell from 7–8 bp (2019–24) to about 1–2 bp (since Oct 2024).

**Verdict:** the overnight effect is real. Before costs it is the strongest pattern in this repo outside the flows
(t ≈ 2.9 on each index). After costs it pays only at today's spreads and only if swap-free status holds:
- At today's spreads and zero swap it nets roughly +6–9% a year at 1x.
- With swaps it is about zero.

Two warnings:
1. Buying and holding the same index at zero swap would have earned more. The daily round trip costs about 4% a
   year even at today's spreads, so the overnight version mainly buys a smaller drawdown.
2. Holding every night is exactly what Exness flags as "persistent overnight positions".
