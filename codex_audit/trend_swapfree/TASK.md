# Time-series momentum (trend following) on a swap-free Exness account: is this a real edge for a EUR 1,000 trader?

Background: ~200 short-term ideas failed after costs in this repository; the only working trades are scheduled
flows (USDJPY gotobi, GBPUSD month-end fix). Daily trend following failed earlier ONLY because of overnight CFD
financing. Exness says Standard accounts are swap-free by default on eligible instruments (it lists EURUSD, GBPUSD,
USDJPY, XAUUSD and all indices), but status depends on trading activity and "persistent large overnight positions"
can lose it. Work only in this folder; do not read other code or results here except the data below.

## Part 1: research (RESEARCH.md, cite every source with a link; do not invent)
- Exness swap-free rules today: which instruments, how status is gained/lost, what "persistent" means, and the
  current published swap rates (long/short) for EURUSD, GBPUSD, USDJPY, XAUUSD, US500, USTEC if the site shows them.
- The evidence for time-series momentum: Moskowitz, Ooi & Pedersen (2012, JFE), Hurst, Ooi & Pedersen (2017, "A
  Century of Evidence on Trend-Following Investing"), and anything on its performance after 2015. Summarise
  realistic Sharpe ratios and drawdowns.
- Minimum position sizes on Exness Standard vs Standard Cent for these instruments, and what that means for
  diversifying EUR 1,000 across several markets.

## Part 2: rules (RULES.md, before computing any return)
One main, literature-standard portfolio and at most 3 pre-declared variants. For example: signal = average of the
signs of the 1-, 3- and 12-month returns; each instrument sized to an equal share of a 10-15% annual portfolio
volatility target using its recent volatility; weekly rebalance; leverage cap. Universe A = swap-free-eligible
only (EURUSD, GBPUSD, USDJPY, gold, US500, NASDAQ, DAX, FTSE); universe B = A plus other FX majors and silver.

## Part 3: backtest (research.py, results.json, REPORT.md)
Data (read only):
- E:/Projects/New folder/liquidity_sweep/data/daily_yahoo.parquet: daily closes (columns date, sym, open, high,
  low, close) back to the 2000s for EURUSD=X, GBPUSD=X, USDJPY=X, AUDUSD=X, NZDUSD=X, USDCAD=X, USDCHF=X, GLD, SLV,
  SPY, QQQ, ^GSPC, ^GDAXI, ^FTSE, ^N225, ^IRX (3-month T-bill), BTC-USD.
- E:/Projects/New folder/liquidity_sweep/data/*_m1.parquet: Exness 1-minute bid/ask (EURUSDm, GBPUSDm, USDJPYm from
  2016 incl. *_2016_m1, XAUUSDm from 2015-08 incl. XAUUSDm_2015_m1, US500m/USTECm/DE30m/UK100m from 2019-08) - use
  them to measure realistic spreads by year and to check that the daily signals trade the same on Exness prices.
Costs: pay the spread on every rebalance trade (by instrument and year). Two financing cases: (i) zero swap
(swap-free kept), (ii) a realistic swap estimate (state your assumption, e.g. rate differential plus a broker
markup, or the published Exness rates if you find them).
Report the full history (as long as the data allows), with the design period up to 2015 and the hold-out 2016-2026
judged once, and for EUR 1,000: (a) 2016-10-01..2026-09-30, (b) 2024-10-01..2026-09-30, (c) 2026-01-01..2026-09-30 -
final balance, annual return, Sharpe, max drawdown, worst year. Compare with simply holding the same instruments
long and with cash. Say whether the result is feasible at EUR 1,000 given minimum lot sizes (Standard vs Cent).
Finish REPORT.md with an honest verdict and, if positive, the exact portfolio you would forward-test on demo.

Memory: about 4 GB free; daily data is small, but load minute files one at a time and only the columns you need.
