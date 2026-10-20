# Research and backtest: do SMC / price-action / support-resistance breakout methods make money?

Many retail traders say they make money with Smart Money Concepts (liquidity sweeps, break of structure, change of
character, fair value gaps, order blocks, premium/discount, kill zones) and with classic support/resistance
breakouts, breakdowns and "break and retest". Find out, honestly, whether any precise version of these survives real
costs. Work only in this folder; write everything here.

## Part 1: research (write RESEARCH.md)
Use web search if it is available to you. Find and cite (title, authors/source, year, link) anything that gives
EVIDENCE rather than marketing:
- studies of retail / day-trader profitability (e.g. day-trader cohort studies, broker CFD loss disclosures,
  prop-firm payout statistics);
- any peer-reviewed or well-documented test of support/resistance, breakouts, stop-loss clustering, round numbers,
  liquidity grabs / stop hunts, fair value gaps or order blocks;
- what successful practitioners with VERIFIED records actually do (be sceptical: unverified screenshots and course
  sellers are not evidence; say so when that is all there is).
Say clearly what is known, what is plausible, and what is myth. Do not invent citations: if you cannot verify a
source, leave it out.

## Part 2: rules (write RULES.md BEFORE computing any strategy return)
From Part 1, write up to 8 PRECISE, mechanical rules that capture how these methods are really traded, e.g.
- break of structure on M15/H1 in the H4/daily trend direction, then entry on the retest of the fair value gap or
  order block it left, stop beyond the swing, target the next liquidity pool / 2-3R;
- equal highs/lows swept, followed by a displacement candle and a fair value gap, entry on the FVG retest;
- support/resistance from swing points or prior-day/week levels: breakout continuation, breakdown continuation,
  and break-and-retest entries; range-bound fades at the same levels as the opposite case;
- session filters (London / New York kill zones) if the method uses them.
Every rule must say exactly: timeframe, how levels/swings/FVGs are defined, entry, stop, target, time exit, max one
position at a time.

## Part 3: backtest (write research.py, results.json, REPORT.md)
Data (read only; UTC 1-minute bid/ask bars, Exness Standard retail feed; columns bopen bhigh blow bclose aopen ahigh
alow aclose; the files in data/ also have n = ticks in the minute, up / dn = ticks whose mid rose / fell):
- E:/Projects/New folder/liquidity_sweep/data/: XAUUSDm_m1 (2019-01..2026-09) + XAUUSDm_2015_m1 (2015-08..2018),
  EURUSDm_m1, GBPUSDm_m1, USDJPYm_m1 (2019-01..2026-09) + EURUSDm_2016_m1, GBPUSDm_2016_m1, USDJPYm_2016_m1
  (2016-2018), USTECm_m1 (NASDAQ 100), US500m_m1, US30m_m1, DE30m_m1 (2019-08..2026-09).
Use gold, NASDAQ (USTEC), US500, EURUSD and GBPUSD at least.

Honesty rules (non-negotiable):
- real bid/ask: buy at the ask, sell at the bid; entries/exits at the next bar open after a signal; when the stop
  and the target are inside the same bar the stop wins; intraday holds only, or estimate swap/financing if held
  overnight and say what you assumed;
- choose any free parameter on data up to 2021-12-31 only; judge ONCE on 2022-01-01..2026-09-30; no re-tuning
  after looking at the hold-out;
- compare each rule with the same entries in a random direction (seeded) and say whether it beats that;
- Bonferroni across the rules you test;
- report, for EVERY rule: (a) 2016-10-01..2026-09-30 (or from 2019-08 for indices) and (b) 2024-10-01..2026-09-30:
  trades, average R, t, win rate, and EUR 1,000 compounded at 2% risk per trade (final balance, max drawdown).

Already tested here and failed (do not just repeat them; build on them): plain sweep-and-reclaim reversals at prior
day highs/lows, overnight/Asia/opening ranges (gold, FX, NASDAQ, S&P, Dow); order-block limit entries; tick-delta
order flow; M5 indicator grids; trend following on daily CFDs.

Memory: this PC has about 4 GB free and an earlier run was killed for low memory. Load only the columns you need,
one or two symbols at a time, resample to M5/M15 early, and free frames with del + gc.collect().

## Part 4: the published, research-backed side of breakouts and order flow (same honesty rules)
Find the papers yourself (web search), read how each strategy is defined, implement it as published on our data,
and test it exactly like Part 3 (add these to RULES.md before running them):
- Opening-range breakout day trading on the US index (Zarattini, Barbon and Aziz, around 2023-2024, SSRN; also
  their follow-up that restricts it to "stocks in play" by relative volume - use the tick count n as the volume
  proxy where the paper uses volume);
- intraday momentum with "noise area" boundaries and a VWAP / boundary trailing exit on the S&P 500 (Zarattini, Aziz
  and Barbon, "Beat the Market", around 2024);
- market intraday momentum: the first half-hour return predicting the last half-hour (Gao, Han, Li and Zhou,
  Journal of Financial Economics, 2018);
- stop-loss and take-profit clustering at round numbers in FX (Carol Osler, 2003 and 2005): do trends continue
  faster after crossing a round number than after crossing an arbitrary level, and do they reverse more often at
  round numbers? Use EURUSD, GBPUSD, USDJPY and arbitrary-level placebos.
Then ORDER FLOW: explain in RESEARCH.md what real order flow is (exchange volume, aggressor side, footprint/delta,
cumulative delta, depth of market), what the evidence says about its predictive power at a retail trader's
horizon (e.g. order-flow imbalance research), and what a CFD trader on MT5 can and cannot see (our files are a
broker's quotes, not exchange trades). Test any proxy our data allows (tick count n, tick-rule buy/sell counts) as
a confirmation filter on the breakout rules, and say whether real futures order-flow data would be worth buying
and from where.

Finish with REPORT.md: a table per rule, an honest verdict for each, an overall verdict on "people make money with
SMC / breakouts / order flow", and what (if anything) deserves a forward test.
