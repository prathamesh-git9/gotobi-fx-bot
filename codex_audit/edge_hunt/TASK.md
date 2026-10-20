# Edge hunt: find ANY technical edge that survives real retail costs (or show honestly that none does)

The user wants an edge. Search widely, technically and honestly. Work only in this folder; do not read other code or
results in this repository except the data listed below and ../smc_research/REPORT.md (what already failed).

## Data (read only; UTC 1-minute bid/ask bars, Exness Standard retail feed)
Columns bopen bhigh blow bclose aopen ahigh alow aclose; files in data/ also have n (ticks in the minute) and up/dn
(ticks whose mid rose/fell). Pip 0.0001 FX, 0.01 JPY pairs; quote gold/indices in price points or % of price.
- E:/Projects/New folder/liquidity_sweep/data/: XAUUSDm_m1 (2019-01..2026-09) + XAUUSDm_2015_m1 (2015-08..2018),
  EURUSDm_m1, GBPUSDm_m1, USDJPYm_m1 (2019-01..2026-09) + *_2016_m1 (2016-2018), USTECm_m1, US500m_m1, US30m_m1,
  DE30m_m1, UK100m_m1 (2019-08..2026-09), daily_yahoo.parquet (daily closes: date, sym, close, many indices/FX).
- E:/Projects/New folder/liquidity_sweep/strategies/explore/data/: EURJPYm, AUDJPYm, AUDUSDm, USDCNHm, XAGUSDm, EURGBPm,
  GBPJPYm, CADJPYm, CHFJPYm, AUDNZDm (2016-01..2026-09), BTCUSDm (2019-01..2026-09), _m1.parquet (no n/up/dn).
Known data facts: Exness cut US index spreads from 3-4 bp to ~0.9 bp in Q4 2024 and to ~0.4-0.65 bp in Q3 2026; US
index quotes stop at 15:59 New York on many days in 2019-2023 (do not schedule exits at 16:00).

## Already tested and failed here (do not repeat): liquidity sweeps of every kind, FVG/BOS/order blocks, break and
retest, prior-day and channel breakouts, opening-range breakout, first/last half-hour momentum, round numbers,
tick-delta "order flow", M5 indicator grids, RSI(2) dips, Bollinger/volume fades, z-score pairs, carry with VIX
filter, NFP drift, every fix/auction/calendar idea except the two that work (USDJPY gotobi, GBPUSD month-end fix).
Claude is separately testing the European-open overnight drift (Boyarchenko et al.), opening-gap fills, and a
portfolio of the existing keepers - do not do those.

## Search these (write RULES.md with exact rules BEFORE computing returns; one fixed version per idea)
A. Classic technical setups with long track records: Toby Crabel narrow-range NR4/NR7 and inside-day breakouts;
   Larry Williams volatility breakout (open +- k x previous day's range, k fixed in advance); Connors & Raschke
   "Turtle Soup" (failed 20-day breakout reversal); Donchian 20/55-day breakout and moving-average trend following on
   daily bars (with financing, see E); Connors-style pullbacks in a 200-day uptrend (N-day low) on indices and gold;
   London breakout of the Asian range in the breakout direction. Use FX majors, gold, NASDAQ, S&P, DAX.
B. Time-of-day / day-of-week seasonality map: average return of every hour (and each weekday) per instrument after
   spread. Pick hours ONLY on 2016-2021 (2019-08..2021 for indices) with a false-discovery-rate control, then trade
   those hours once on 2022-2026 and report.
C. Scalping at TODAY's costs: holding periods of 1-15 minutes on US500, USTEC, XAUUSD, EURUSD, using only the
   low-spread era (design 2024-10..2025-09, test once 2025-10..2026-09) plus an extra 0.1 pip / 0.2 bp slippage per
   side. Ideas: reversal after an extreme 1-minute move, continuation after a tick-activity (n) burst, micro breakouts
   of the last 15-60 minutes' range, first minutes after the hour, the minutes around the US cash open.
D. Machine learning, done properly: gradient boosting (scikit-learn HistGradientBoosting) on hourly technical
   features (returns over several lookbacks, volatility, range position, hour, weekday, distance to moving averages,
   tick activity) predicting the next hour's / next day's direction; walk-forward with yearly retraining, trade only
   above a probability threshold fixed in the design years, real costs, compared with random direction. Report the
   out-of-sample result honestly, including if it is zero.
E. Financing: research on the web what Exness charges for overnight swaps (and whether swap-free terms apply to
   standard retail accounts, and for which instruments). If holds can be swap-free, re-test daily trend following
   (from A) with zero swap; otherwise estimate the swap and say what you assumed.

## Honesty rules (non-negotiable)
Buy at the ask, sell at the bid; next-bar-open entries; stop wins ties inside a bar; free parameters chosen on the
design period only; judge once on the hold-out (2022-01..2026-09, or the scalping split above); compare each rule
with the same entries in a random direction (seeded); Bonferroni or FDR across everything you test; say if you had
to look at the hold-out to fix a bug. For EVERY rule report (a) 2016-10-01..2026-09-30 (indices from 2019-08) and
(b) 2024-10-01..2026-09-30: trades, average R (or % per trade), t, win rate, EUR 1,000 compounded at 2% risk per trade
(final, max drawdown).

Memory: about 4 GB free, and Claude's own backtests run at the same time. Load only needed columns, one or two
symbols at a time, resample early, free memory with del + gc.collect(). Never load all files at once.

Finish with REPORT.md: a table per idea, an honest verdict for each, and a direct answer to "is there an edge
anywhere?" - name the single best candidate (if any), how confident you are, and what forward test would confirm it.
