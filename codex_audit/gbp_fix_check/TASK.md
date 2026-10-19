# Independently check one candidate rule. Try hard to break it.

Work only in this folder; do not read other code or results in this repository.

Rule (fixed; do not tune it): on the LAST London business day of each month (UK bank holidays via the python
'holidays' package, holidays.UK), BUY GBP/USD at 15:45 London time (bar open, ask), sell at 16:00 London time
(bar open, bid), 25-pip stop (if a bar's bid low touches entry-25 pips, exit at -25 pips). London time includes
daylight saving. Claim: GBP/USD rises into the month-end 4 pm WM/Reuters fix.

Data (read only, UTC 1-minute bid/ask bars, columns bopen bhigh blow bclose aopen ahigh alow aclose):
- E:/Projects/New folder/liquidity_sweep/data/GBPUSDm_2016_m1.parquet (2016-2018), GBPUSDm_m1.parquet
  (2019-01..2026-09), GBPUSDm_2026_m1.parquet (2026), same for EURUSDm (EURUSDm_2016_m1, EURUSDm_m1,
  EURUSDm_2026_10_m1). Exness Standard feed, real spreads.
- E:/Projects/New folder/liquidity_sweep/strategies/month_end_fix/data/GBPUSD_hd_bid_m1.parquet and
  EURUSD_hd_bid_m1.parquet: HistData 2006-2015, BID ONLY (bopen bhigh blow bclose), index already in naive UTC.
  You must model the ask yourself (say how, and stress it).

Do:
1. Reproduce the rule 2006-2026: trades, mean pips, t, win rate, per-year pips, 2006-15 vs 2016-21 vs 2022-26.
2. Control: the same 15:45-16:00 trade on every other London business day; and on the last business day of the
   month but at other times (e.g. 14:45-15:00, 16:15-16:30).
3. Robustness: entry 15:40/15:50, exit 15:58/16:02, stop 15/40/none; spread +0.5/+1 pip; stop slippage 3 pips;
   exclude the 5 best trades; month-end defined as last calendar weekday instead.
4. Same trade on EUR/USD. Is there a sensible economic reason it would be sterling-only?
5. Permutation test: 10,000 random sets of the same number of business days in the same years; how often does a
   random set beat the month-end mean?
6. EUR 1,000 compounded at 2% risk (25-pip stop = 1R) from 2016 and from 2025-01-01 to 2026-09-30.
Write research.py and REPORT.md with an honest verdict: REAL EDGE / WEAK OR FRAGILE / NOT AN EDGE.
