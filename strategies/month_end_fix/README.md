# Strategy 2: month-end 4 pm London fix (research only, no bot)

Kept apart from the gotobi bot on purpose: nothing here imports or changes `gotobi_bot/`, its config or its tests.
It only reads `src/flow_edges.py` (price loader) and the Exness minute data in `data/`.

| Script | What it tests |
|---|---|
| `backtest.py` | The friend's rule as written: EURUSD 15:30-15:55 UTC on month-end, short if the S&P 500 (in EUR) beat the DAX month to date, else long, stop 15. Also the London-time version. |
| `variants.py` | 756 modifications fixed in advance (EURUSD/GBPUSD, 7 windows, 6 direction rules, 3 day sets, 3 stops), judged on 2016-21 and 2022-26 separately against ordinary days. |
| `fetch_old.py` | EURUSD/GBPUSD 2006-2015 bid minutes from HistData (data never used to choose anything). |
| `out_of_sample.py` | The 5 grid survivors, frozen, run on 2006-2015 with the Exness 2016-18 spread profile (+0.5 pip stress). |
| `stress.py` | The best one: stop slippage, per year, and the same trade on EURUSD. |
| `last15.py` | Buy GBPUSD 15:45-16:00 London on month-end (picked after the grid for being stable at every stop). |

## Results (19 Oct 2026)

- **The friend's rule loses**: -0.96 pips/trade (t -0.91), the same as the identical trade on ordinary days;
  EUR 1,000 from 2016 -> EUR 532 at 6% risk, from Jan 2025 -> EUR 955. Its "15:30 UTC is always 11:30 New York"
  is wrong (10:30 in winter), and in summer 15:30 UTC is after the 4 pm fix, not before it.
- **The only thing that survives** is not the conditional signal at all: GBPUSD rises into the month-end fix.
  Buy GBPUSD 15:45 -> 16:00 London, last London business day, stop 25:
  2006-15 (unseen) +5.32 pips (t 2.69), 2016-26 +3.50 (t 1.89), all 248 trades +4.38 (t 3.24), 16/21 years up,
  +3.82 with stops 3 pips worse. EUR 1,000 from 2016 -> EUR 1,405 at 2% / EUR 2,490 at 6% (worst drop 37%);
  from Jan 2025 -> EUR 1,136 / EUR 1,445.
- Caveats: EURUSD does not show it (so it is not a plain dollar flow, and there is no clear reason why sterling),
  2022-24 were flat, 12 trades a year, and the exit sits on the fix minute where spreads widen.
  Much weaker than gotobi (t 6.6 over 20 years, ~70 trades a year). Forward-test on paper before any bot.
