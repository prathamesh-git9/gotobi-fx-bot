# Round 2: test these specific scheduled-flow ideas honestly (none of them has been tested before)

Work only in this folder; do not read other code or results in this repository. Read-only data (UTC, 1-minute
bid/ask bars from the Exness Standard feed, columns bopen bhigh blow bclose aopen ahigh alow aclose):
- E:/Projects/New folder/liquidity_sweep/data/EURUSDm_m1.parquet, GBPUSDm_m1.parquet, USDJPYm_m1.parquet,
  XAUUSDm_m1.parquet (2019-01 .. 2026-09); EURUSDm_2016_m1, GBPUSDm_2016_m1, USDJPYm_2016_m1 (2016-2018);
  XAUUSDm_2015_m1 (2015-08 .. 2018); US500m/US30m/USTECm/DE30m/UK100m_m1 (indices, 2019-08 .. 2026-09).
- data/histdata/USDJPY_hd_model_2006_2015_m1.parquet: USD/JPY 2006-2015, same columns (bid from HistData, ask =
  bid + a modelled Exness spread). Use it as an extra untouched test for the Japan ideas.
- data/events_calendar.csv: columns event,date,time_utc. event 'fomc' = scheduled FOMC statements 2016-2027 with
  the UTC release time; 'boj' = BoJ decision days (date only).
- data/daily_yahoo.parquet: daily closes (date, sym, close) for ^GSPC ^GDAXI ^FTSE ^N225, SPY etc.
Holidays: the python 'holidays' package is installed (holidays.NYSE, holidays.Japan, holidays.UK).

Ideas to test (write the exact rules down BEFORE looking at results; you may add 1-3 of your own of the same kind):
1. Pre-FOMC drift (Lucca & Moench 2015): long US500 (also US30, USTEC) from 14:00 New York the day before a
   scheduled FOMC statement to 15 minutes before the release. Also the same window in USD/JPY, EUR/USD, gold.
2. Pre-holiday effect: long US500 into the close of the trading day before each NYSE holiday (pick the window
   on the selection period).
3. Japanese "toshin" (investment trust) outflows: Japanese funds buy foreign assets early in the month. USD/JPY
   in the Tokyo morning (around the 09:55 JST fix) on the first 1-3 Japanese business days of each month.
4. Japanese half-year/year-end repatriation: USD/JPY over the last ~10 Japanese business days of September and
   March (and the reversal after).
5. Weekend gap: fade (or follow) the Sunday-open gap in EUR/USD, GBP/USD, USD/JPY, gold, from the first liquid
   minute after the open to a fixed exit.
6. BoJ decision days: USD/JPY in the Tokyo session before the decision.

Rules for honesty:
- Real spread (bid/ask). Trades at bar opens. If a bar touches both stop and target, the stop wins. Note any
  CFD financing a multi-day hold would pay (assume about 6%/yr on index notional, and say so).
- Choose each rule on 2016-2021 (or 2019-2021 where data starts later), then judge it ONCE on 2022-2026-09-30.
  For Japan ideas also report 2006-2015.
- Control: the same trade on ordinary days/times. Report t-stats, per-year pips, and correct for the number of
  ideas tested (state the threshold you used).
- For anything that survives, compound EUR 1,000 (treat as USD-equivalent if needed, say so) at 2% risk per
  trade: (a) from the earliest data to 2026-09-30, (b) from 2025-01-01 to 2026-09-30. Final balance, max
  drawdown, trades, worst year.
Write the code as research.py and finish with REPORT.md: every idea tested (including failures), the survivors,
and an honest verdict on whether any of them is worth automating.
