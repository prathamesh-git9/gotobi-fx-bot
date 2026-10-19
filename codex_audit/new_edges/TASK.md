# Find a NEW flow-driven trading edge (not the USD/JPY gotobi trade) and backtest it honestly

Work only in this folder; do not read other code or results in this repository. Read-only data you may use
(UTC, 1-minute bid/ask bars from the Exness Standard feed, columns bopen bhigh blow bclose aopen ahigh alow aclose):
- E:/Projects/New folder/liquidity_sweep/data/EURUSDm_m1.parquet, GBPUSDm_m1.parquet, USDJPYm_m1.parquet,
  XAUUSDm_m1.parquet (2019-01 .. 2026-09), USDJPYm_2016_m1.parquet (2016-2018), XAUUSDm_2015_m1.parquet
  (2015-08 .. 2018), and, if present when you start, EURUSDm_2016_m1.parquet and GBPUSDm_2016_m1.parquet
  (2016-2018). US500m/US30m/USTECm/DE30m/UK100m_m1.parquet (indices, 2019-08 .. 2026-09).
- E:/Projects/New folder/liquidity_sweep/data/daily_yahoo.parquet: daily closes (columns date, sym, close) for
  ^GSPC ^GDAXI ^FTSE ^N225, SPY QQQ GLD, EURUSD=X GBPUSD=X USDJPY=X AUDUSD=X USDCHF=X etc., 1950..2026-10.

The gotobi trade works because Japanese importers must buy dollars at the 09:55 Tokyo fix on set days: a
forced, predictable flow at a known time. Look for OTHER effects of that kind: forced or scheduled flows at
known times (e.g. month-end/quarter-end rebalancing at the London 4 pm WM/Reuters fix, the gold London fixes,
index rebalances, other fixes, holiday or session effects). Use your own knowledge of the published research.

Rules for honesty:
- Include the real spread (bid/ask). Trades at bar opens. If a bar touches both stop and target, the stop wins.
- Choose each rule on 2016-2021 (or 2019-2021 where data starts later), then judge it ONCE on 2022-2026.
- Compare with a control: the same trade on ordinary days/times. Report t-stats and per-year pips.
- For anything that survives, compound EUR 1,000 (treat as USD-equivalent if needed, say so) at a sensible
  risk per trade: (a) from 2016 (or the earliest data) to 2026-09-30, (b) from 2025-01-01 to 2026-09-30.
  Report final balance, max drawdown, trades, worst year.
Write the code as research.py and finish with REPORT.md: every idea tested (including failures), the
survivors, and your honest verdict on whether any of them is worth automating.
