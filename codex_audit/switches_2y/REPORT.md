# Independent USD/JPY Gotobi backtest

Run `python backtest_2y.py` in this folder to reproduce the tables. I used only the two price files named in TASK.md and `holidays.Japan`; I did not inspect other repository code or results. **EUR figures below are USD-equivalent account units**, starting at 1,000. No historical EUR conversion series was provided.

## Rules and accounting

The test period is 2024-10-17 through 2026-10-16, inclusive. The earlier check is 2019-01-01 through 2024-10-16, inclusive. I generate the nominal 5/10/15/20/25/30 dates, move nonbusiness dates back using Japanese holidays and the specified New Year closure, skip moved 25 December or 1 January, and count a moved date once if two nominal dates land on it. All times are treated as UTC. A Sunday entry uses the first Sunday bar plus 15 minutes.

Orders use the **open** quote of the specified minute; stops and the long target use minute highs/lows starting with the entry minute. Long closes use bid, short closes use ask. A stop wins an ambiguous same-bar stop/target touch. Gaps through a stop or target fill at the next bar's open. The 00:54 and 01:25 timed exits execute at those bars' opens, before their intrabar extremes. Missing required bars and entry spreads over 5 pips skip the trade. Position size floors to 0.01 standard lot (assumed 100,000 USD/lot), and JPY P/L is converted at the exit USD/JPY price. Results include the quoted spread and exclude commissions, financing, and slippage. Drawdown uses **closed-trade equity peaks and troughs**. The 60-long kill condition is checked after each completed long, once 60 longs exist; the 50% equity kill condition is checked after each trade. A triggered kill prevents subsequent entries.

## Two-year base case

At **6% risk**, final balance is **1,000 → 4,513.61 EUR-equivalent**. Maximum closed-trade drawdown is **39.76%** over **263 trades**. Overall win rate is **62.36%**, with **5.64 pips/trade**. The worst calendar month by realized P/L is **July 2025, −302.94**. **Neither kill condition trips.**

| Side | Trades | Win rate | Pips/trade |
|---|---:|---:|---:|
| Long | 126 | 65.87% | +7.19 |
| Short | 137 | 59.12% | +4.23 |

There are 139 scheduled test dates, yielding 278 possible legs. Fifteen entries are skipped for spreads above 5 pips; no required entry/exit bars are missing in this period. In the earlier period, 19 legs have missing required bars and 40 exceed the spread limit. All listed switches change **one setting at a time** from the 6% base, and the target changes apply only to longs.

## Switches and candidate filters: 2024-10-17 to 2026-10-16

| Variant | Final EUR-equivalent | Max DD | Trades | Pips/trade |
|---|---:|---:|---:|---:|
| Base 6% | 4,513.61 | 39.76% | 263 | +5.64 |
| Risk 2% | 1,632.53 | 14.67% | 263 | +5.64 |
| Risk 4% | 2,740.96 | 28.09% | 263 | +5.64 |
| Risk 8% | 7,319.54 | 49.74% | 263 | +5.64 |
| Risk 10% | 2,648.87 | 53.25% | 113 | +5.42 |
| No take profit | 4,833.64 | 39.09% | 263 | +6.09 |
| Take profit 20 pips | 3,503.92 | 33.13% | 263 | +4.67 |
| Take profit 50 pips | 4,942.01 | 38.80% | 263 | +6.04 |
| Stop 35 pips | 1,833.17 | 50.85% | 133 | +3.19 |
| Stop 75 pips | 3,020.64 | 29.76% | 263 | +5.61 |
| Long only | 2,460.84 | 35.41% | 126 | +7.19 |
| Short only | 1,822.43 | 9.91% | 137 | +4.23 |
| No kill switch | 4,513.61 | 39.76% | 263 | +5.64 |
| Spread ≤2 pips | 4,132.70 | 39.76% | 259 | +5.41 |
| Omit shifted dates | 3,337.46 | 18.48% | 175 | +6.71 |
| Omit nominal 30th | 3,634.39 | 37.75% | 222 | +5.70 |
| Omit Mondays | 3,696.92 | 40.41% | 242 | +5.33 |
| Trend aligned | 1,412.25 | 27.69% | 124 | +2.98 |

The 10% case triggers the **50% equity drawdown** kill after 113 trades; the 35-pip stop case does likewise after 133. A completed loss can carry drawdown past the 50% threshold before trading stops. The no-kill case is identical to base because neither condition fires at 6%.

## Earlier-period check: 2019-01-01 to 2024-10-16

Each variant starts again at 1,000, with its own compounding and kill state. This period is longer than the two-year test, so final balances are **not directly comparable across periods**; compare a variant with its base in the same period. I checked all switches as well as every filter proposed here.

| Variant | Final EUR-equivalent | Max DD | Trades | Pips/trade |
|---|---:|---:|---:|---:|
| Base 6% | 6,922.98 | 29.41% | 751 | +2.61 |
| Risk 2% | 1,879.93 | 10.32% | 751 | +2.61 |
| Risk 4% | 3,722.90 | 20.01% | 751 | +2.61 |
| Risk 8% | 12,815.40 | 38.06% | 751 | +2.61 |
| Risk 10% | 22,408.61 | 46.11% | 751 | +2.61 |
| No take profit | 5,249.82 | 25.93% | 751 | +2.30 |
| Take profit 20 pips | 5,666.98 | 27.56% | 751 | +2.33 |
| Take profit 50 pips | 7,909.38 | 29.86% | 751 | +2.79 |
| Stop 35 pips | 22,314.87 | 35.15% | 751 | +2.68 |
| Stop 75 pips | 4,093.02 | 23.35% | 751 | +2.58 |
| Long only | 3,194.10 | 30.26% | 357 | +3.36 |
| Short only | 2,192.38 | 9.45% | 394 | +1.94 |
| No kill switch | 6,922.98 | 29.41% | 751 | +2.61 |
| Spread ≤2 pips | 7,231.91 | 25.58% | 739 | +2.69 |
| Omit shifted dates | 3,937.69 | 14.18% | 500 | +2.75 |
| Omit nominal 30th | 6,211.04 | 21.51% | 633 | +2.88 |
| Omit Mondays | 6,204.07 | 33.28% | 691 | +2.68 |
| Trend aligned | 2,894.60 | 24.82% | 358 | +3.00 |

The added filters are: a 2-pip spread cap; omitting dates moved from the nominal date; omitting nominal 30ths; omitting Mondays; and a trend check. For the trend check, the last completed active UTC day's bid close is compared with the mean of the last 20 completed active days. A long requires above-mean and a short below-mean. The check uses only completed days available before each entry.

**Which ideas survive both periods?** Omitting shifted dates cuts drawdown materially in both (39.76% → 18.48%; 29.41% → 14.18%) and raises average pips/trade, but removes about one third of trades and lowers final balance in both. Omitting nominal 30ths also raises average pips/trade and lowers drawdown in both, with smaller effects and lower final balance. These are plausible risk-control candidates, not evidence of higher total profit. The 2-pip cap helps only in the earlier period; omitting Mondays and the trend filter do not improve the recent per-trade result. None of these filters demonstrates a robust increase in final balance across both periods.

## Judgment

The **50-pip long target** is the clearest tested parameter improvement: final balance and pips/trade rise against the 30-pip base in *both* periods, while drawdown is about the same. I would still treat the exact 50-pip value as provisional because it was selected from several tested values on the same history. Removing the target and the 35-pip stop are especially unstable across periods. The 75-pip stop consistently cuts drawdown but lowers both final balance and pips/trade. Keeping only shorts also gives low drawdown in both periods, at the cost of much lower return; excluding longs is not supported as a profit improvement. Turning off the kill switch changes nothing at 6% and gives no evidence that it is unnecessary in future losses.

For a 1,000 EUR account, **I would choose 2% risk per trade**. The base's 39.76% realized drawdown is severe; 8% nearly hits the 50% kill threshold and 10% does hit it. At 2%, closed-trade drawdown is 14.67% in the recent test and 10.32% earlier, with the same trades and pips/trade. This risk change controls position size; it does not create an edge. I would consider the 50-pip target for a forward paper test, but would not assume the historical gain will repeat.

## What could be wrong

- **Execution:** Minute OHLC cannot reveal the sequence within a minute. The required stop-first rule handles a stop/target collision, but real fills, gaps, latency, and thin Sunday or rollover liquidity can be worse. Spread is observed at the bar open; commissions, swap, and additional slippage are absent.
- **Account units and contract:** Without EUR/JPY conversion and the actual Exness USDJPYm contract specification, exact EUR P/L, margin needs, and lot rounding are uncertain. The model assumes a standard 100,000 USD lot and USD-equivalent starting balance.
- **Drawdown:** The reported figure uses realized trade closes. Open-position drawdowns and margin liquidation could be larger, particularly at high risk. Risk sizing uses the entry conversion quote; realized stop loss varies slightly with the exit quote.
- **Data gaps and clocks:** Required missing bars cause skips. UTC timestamps and the broker's historical bid/ask quotes are assumed accurate. The earlier file starts on 2019-01-02, and the final October file ends on 2026-10-16. Holiday handling depends on `holidays.Japan`'s historical calendar; a different definition of Japanese business day can alter moved dates.
- **Selection:** The older sample is a useful crosscheck but not a true untouched forward test after looking at several switches and filters. Broker-specific historical conditions, regime changes, and the small two-year sample can make the apparent edge or the 50-pip improvement disappear.
