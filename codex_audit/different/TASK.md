# Find something DIFFERENT that might work (not calendar flows), and backtest it honestly

Work only in this folder; do not read other code or results in this repository except the data listed here.

Data (read only, UTC 1-minute bid/ask bars, Exness Standard retail feed; columns bopen bhigh blow bclose aopen ahigh
alow aclose; pip = 0.01 for JPY pairs, 0.0001 other FX):
- E:/Projects/New folder/liquidity_sweep/data/: EURUSDm_m1, GBPUSDm_m1, USDJPYm_m1, XAUUSDm_m1 (2019-01..2026-09),
  EURUSDm_2016_m1, GBPUSDm_2016_m1, USDJPYm_2016_m1 (2016-2018), XAUUSDm_2015_m1 (2015-08..2018),
  US500m/US30m/USTECm/DE30m/UK100m_m1 (2019-08..2026-09), daily_yahoo.parquet (daily closes: date, sym, close; many
  indices, ETFs and FX back to 1950).
- E:/Projects/New folder/liquidity_sweep/strategies/explore/data/: EURJPYm, AUDJPYm, AUDUSDm, USDCNHm, XAGUSDm,
  EURGBPm, GBPJPYm, CADJPYm, CHFJPYm (2016-01..2026-09), BTCUSDm (2019-01..2026-09), _m1.parquet.

ALREADY FAILED here, do not repeat: liquidity sweeps, ICT/order blocks, tick-delta order flow, M5 indicator rule
grids, trend following on CFDs, turn of the month, overnight drift, pre-FOMC, pre-holiday, weekend gaps, every fix /
auction / expiry idea, holiday reopenings, tax days, Bitcoin funding/CME gap/ETF NAV, Japanese flows other than gotobi.
ALREADY WORKS (do not retest): USD/JPY gotobi, GBP/USD into the month-end 4 pm fix.

Invent up to 8 DIFFERENT ideas with a real economic reason: cross-asset lead-lag (e.g. US500 -> USDJPY, US close ->
DAX open), relative value / pairs (gold/silver, EURJPY vs USDJPY*EURUSD, index pairs), volatility regimes, carry,
post-shock drift or reversal, cross-sectional FX momentum, etc. Write exact rules in RULES.md BEFORE computing returns.

Honesty rules: real bid/ask spread; bar opens; stop wins ties; estimate overnight financing/swap for multi-day holds
(say what you assumed). Choose free parameters on 2016-10..2021-12 (2019-08.. for indices/BTC), judge ONCE on
2022-01..2026-09. Control/benchmark: the same trade with a random or no signal. Bonferroni across ideas.

Report, for EVERY idea: (a) last 10 years 2016-10-01..2026-09-30 and (b) last 2 years 2024-10-01..2026-09-30:
trades, pips/trade, t, win rate, and EUR 1,000 compounded at 2% risk per trade (final balance, max drawdown).
Write research.py and REPORT.md with an honest verdict for each idea.
