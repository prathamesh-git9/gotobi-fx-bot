# Independent audit: does this USD/JPY "gotobi" strategy really make money?

You are an independent quant auditor with no stake in the answer. The owner is about to run this strategy with
real money (starting around EUR 100) and wants a BRUTAL, unbiased, end-to-end backtest and verdict. Your job is
to find out whether it works, not to confirm that it does. If it is overfit, fragile, or only works because of a
modelling mistake, say so plainly.

## Independence rules (important)
- Read ONLY the data files listed below. Do NOT open anything else in this repository: no README/markdown files,
  no code under src/, bot/ or tests/, nothing under results/, no git history. They contain another analyst's code
  and conclusions; the whole point is an independent implementation written from scratch.
- Write everything you produce inside `codex_audit/` (this folder). Do not modify or delete anything outside it.
- Do not commit anything to git.

## Honest context on how the rules were found (relevant for judging overfitting)
- The base rule (buy USD/JPY the afternoon before a gotobi day, sell just before the 09:55 JST Tokyo fix) came
  from a claim posted online.
- The +30 pip take-profit and the post-fix short were then chosen after trying about 108 variants (filters,
  stops, exits, extra trades) on 2016-2021 data, with 2022-2026 held out. So multiple-testing risk is real.

## The strategy, exactly as the trading bot executes it (all times UTC; 1 pip = 0.01 JPY)
Gotobi days:
- The 5th, 10th, 15th, 20th, 25th and 30th of each month (February has no 30th, so no trade for it; there is no
  31st rule).
- A gotobi day that is not a business day moves to the business day before (repeat until it is one). Not a
  business day = Saturday, Sunday, a Japanese public holiday (Python `holidays.Japan()`), 31 Dec, or 1-3 Jan.
  Moved days can coincide (e.g. a 5 Jan can move back to 30 Dec): trade each resulting date once.
- Skip the day if the resulting date is 25 Dec or 1 Jan (FX market closed).
- The Tokyo fix is 09:55 JST = 00:55 UTC on the gotobi day (Japan has no daylight saving).

Trade 1, the long:
- Buy at the ask at 15:55 UTC on the calendar day before the gotobi day.
- If 15:55 falls inside the weekend closure (Sunday, for a Monday gotobi day), buy 15 minutes after prices resume
  on Sunday evening instead.
- If the spread is above 5 pips, wait until it is 5 or less. Give up 120 minutes after the scheduled (or
  reopen-adjusted) time, and never buy with less than 30 minutes left before the exit.
- Stop-loss 55 pips below the entry price and take-profit 30 pips above it, both held on the broker's server. If
  both are touched within the same minute, assume the stop was hit.
- Otherwise sell at the bid at 00:54 UTC on the gotobi day, one minute before the fix.

Trade 2, the post-fix short:
- On the gotobi day, and only if no position is open, sell at the bid at the fix (00:55:00 UTC).
- The bot sends the sell at 00:54:59 and skips it if it cannot be filled by 00:55:05, or if the spread is above
  5 pips at that moment.
- Stop-loss 55 pips above the entry. Buy back at the ask at 01:25 UTC.

Sizing and safety:
- Risk 6% of current equity per trade: choose the size so that the 55-pip stop would lose 6% (the bot computes
  the loss at the stop price including the spread).
- Round down to the broker's lot step. If even the minimum lot would risk more than 6%, skip the trade.
- Kill switch: open no new trades once the last 60 longs sum to less than -6R, or once the balance is 50% below
  its peak.
- Costs: the data is real Exness Standard account bid/ask, so the spread is included; Standard has no
  commission. Overnight swap is NOT in the data: the long is held across the 21:00/22:00 UTC rollover, the short
  is not. Choose your own slippage assumptions and test sensitivity to them.

## Data (read-only)
USD/JPY, Exness Standard ("m" suffix) minute bars:
- Files: `data/USDJPYm_2016_m1.parquet` (2016-01-03 to 2018-12-31), `data/USDJPYm_m1.parquet` (2019-01-02 to
  2026-09-30), `data/USDJPYm_2026_10_m1.parquet` (2026-10-01 to 2026-10-16 20:58).
- Index: minute timestamp, naive UTC. Columns: bopen/bhigh/blow/bclose (bid), aopen/ahigh/alow/aclose (ask),
  and n/up/dn (tick counts).
- A minute with no ticks has no bar: use the last known price.
- De-duplicate any overlap between files.

USD/JPY raw ticks around the fix:
- `data/fix_ticks/USDJPYm_YYYY_MM.parquet`: 00:45-01:35 UTC every day, 2016-01 to 2026-10.
- Index: tick timestamp (naive UTC, 1-second resolution). Columns: bid, ask.
- Use these to check the short's real fill around 00:55:00 and how sensitive it is to arriving a few seconds
  late.

EUR/USD, for EUR accounts:
- `data/EURUSDm_m1.parquet` (2019-01-02 to 2026-09-30) and `data/EURUSDm_2026_10_m1.parquet`: Exness minute
  bars, same columns. Use the mid.
- `data/daily_yahoo.parquet` (columns date, sym, close; sym == "EURUSD=X") for daily closes before 2019, if you
  need them.

Possible extra source for 2006-2015:
- `data/dukascopy/USDJPY_2006_2015_m1.parquet`: Dukascopy minute bid/ask, same column names, a different
  liquidity provider with different spreads. It is being downloaded right now.
- It is complete only when `data/dukascopy/USDJPY_2006_2015_m1.READY` exists. If it is complete by the time your
  2016-2026 work is done, run the full analysis on it too and report it as a separate section. Check its
  integrity yourself.
- Either way, your script must run on it unchanged later.

## What to deliver
1. `codex_audit/backtest.py`: one standalone, reproducible script.
   - Command-line options: `--data FILE [FILE ...]`, `--start`, `--end`, `--risk`.
   - It writes every trade to CSV: date, leg, entry/exit time and price, exit reason, pips, P&L, R.
   - Python with pandas/numpy/pyarrow/holidays is installed (`python`). Do not install anything globally.
2. `codex_audit/REPORT.md`, with the verdict at the top, covering at least the following.
   a. **Per-year returns, every calendar year in the data (2026 = 1 Jan to 16 Oct).**
      - Start a fresh account each 1 Jan at 6% risk, compounding within the year.
      - For each year: trades, win rate, net pips, % return, max drawdown.
      - Do this separately for (A) the plain long with no take-profit and no short, (B) the full strategy (long
        + take-profit + short), and the short alone.
   b. **One continuous run, 2016 to 16 Oct 2026, at 6% risk with the kill switch:** final multiple, max
      drawdown, and whether and when the kill switch would have fired. Also show 3% and 10% risk.
   c. **EUR 100 accounts.** Profits are in JPY; convert to USD at the exit price, then to EUR at that moment's
      EUR/USD.
      - Exness Standard: 1 lot = 100,000 USD, minimum 0.01 lot, step 0.01. Exness Standard Cent: same prices,
        but 100x smaller units, so sizing is effectively exact.
      - Runs: EUR 100 from 1 Jan 2025 to 16 Oct 2026, and EUR 100 from 1 Jan 2026 to 16 Oct 2026.
      - For each: final balance, max drawdown, number of trades, and the October 2026 result.
   d. **Is the edge real?**
      - Significance: t-stat, bootstrap confidence interval of the mean per trade.
      - Control days: the same trades on non-gotobi days.
      - Stability: first half vs second half, 2016-2021 vs 2022-2026.
      - Costs: +0.5 / +1 / +2 pips per trade.
      - Short fill timing: from the ticks, filled 2, 5 and 10 seconds late.
      - Swap: an estimate, or state clearly that you could not get rates.
      - Losing streaks, and Monte Carlo risk of a 50% drawdown at 6% risk.
   e. **A bug and look-ahead audit of your own code**, and anything you could not verify.
   f. **Brutal verdict**: exactly one of REAL EDGE / WEAK OR FRAGILE EDGE / NO EDGE.
      - The reasons, in plain English for a non-expert.
      - What is most likely to make it fail with real money.
      - A realistic expectation for a EUR 100 account over a year.
3. Your final message: the verdict and the key numbers, in at most 40 lines.

Priorities, if time is short:
1. A correct core backtest and the per-year table.
2. The EUR 100 accounts.
3. The robustness tests.
4. The Dukascopy data.
