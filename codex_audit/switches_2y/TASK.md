# Independent 2-year test of a USD/JPY "Gotobi" strategy, and what changes would help

Work only in this folder. Do NOT read any other code or results in this repository (independence matters):
use only the two price files below, read-only.

Data (UTC, 1-minute bid and ask bars of Exness USDJPYm, columns bopen bhigh blow bclose aopen ahigh alow aclose):
- E:/Projects/New folder/liquidity_sweep/data/USDJPYm_m1.parquet       (2019-01 .. 2026-09)
- E:/Projects/New folder/liquidity_sweep/data/USDJPYm_2026_10_m1.parquet (2026-10-01 .. 2026-10-16)

Period: 2024-10-17 to 2026-10-16. Account: EUR 1,000 (treat it as USD 1,000-equivalent if you must; say so).

## The strategy exactly
Gotobi days: the 5th, 10th, 15th, 20th, 25th and 30th of each month (February has no 30th; the 31st never
counts). One on a Saturday/Sunday or a Japanese public holiday (use the `holidays` package, holidays.Japan), or
on 31 Dec or 1-3 Jan, moves to the previous business day. Skip it if the moved day is 25 Dec or 1 Jan.
For each gotobi day D:
1. Long: buy at the ask at 15:55 UTC on the calendar day before D. Stop 55 pips below the entry, take-profit
   +30 pips above, both on the bid. Otherwise sell at the bid at 00:54 UTC on D. (If D-1 is a Sunday the market
   is shut: enter 15 minutes after the first bar of the Sunday reopen.) Skip if the spread is above 5 pips.
2. Short: sell at the bid at 00:55 UTC on D (09:55 Tokyo), stop 55 pips above (on the ask), buy back at the
   ask at 01:25 UTC. Skip if the spread is above 5 pips.
If a bar touches both the stop and the target, count the stop. 1 pip = 0.01.
Sizing: risk_pct of current equity is lost if the 55-pip stop is hit (compounding). Lots rounded down to 0.01.
Kill switch: stop opening trades if the last 60 longs sum to less than -6R, or equity falls 50% below its peak.

## What to produce
1. The base case at 6% risk: final balance, max drawdown, trades, win rate, pips per trade (long and short
   separately), worst month, whether the kill switch trips.
2. Switches (one at a time, from the base case): risk 2/4/8/10%; no take-profit; take-profit 20/50; stop
   35/75; long only; short only; no kill switch.
3. Your own ideas: any filters or indicators you think could help (trend, volatility, day of week, month-end,
   news, etc.). For anything that helps on 2024-10..2026-10, ALSO check it on 2019-01..2024-10 from the same
   file, because a filter picked on two years is easily luck. Say which ideas survive both periods.
4. REPORT.md: a table of every variant (final EUR, max drawdown, trades, pips/trade), and your honest opinion:
   which changes are real improvements, which are curve-fitting, and the risk level you would choose and why.
   Also list anything about the strategy or its testing you think could be wrong.
Write your code as backtest_2y.py in this folder so it can be re-run.
