# Verdict: WEAK OR FRAGILE EDGE

The gotobi effect is visible in these Exness quotes. The **plain long** earned 2,972 pips over 754 trades; the **full rule** earned 4,585 pips over 1,493 trades, including a positive 2022–2026 holdout. Random non-gotobi business days did not show the same pattern. That is evidence of a real historical price effect. It is **not** proof that this exact bot will make money: the extra short averages only 2.17 pips, its fill is at a highly time-sensitive fix, historical swap is unavailable, and the 30-pip take-profit adds only 7 pips to the long over eleven years. At 6% risk the historical continuous drawdown reached **34.5%** even before unmeasured costs.

The full strategy earns 3.07 pips per trade after recorded bid/ask spread. Two more pips of round-trip execution cost cut that to 1.07 pips. If the long also incurs roughly 2.12 pips of unmodeled swap *per long on average*, the residual disappears. A live fill or swap record is therefore decisive. The strategy should be treated as an unproven, fragile implementation of a plausible effect, not as an income plan.

## Reproduction and price model

Run from the repository root:

```powershell
python codex_audit/backtest.py --data data/USDJPYm_2016_m1.parquet data/USDJPYm_m1.parquet data/USDJPYm_2026_10_m1.parquet --start 2016-01-01 --end 2026-10-16 --risk 0.06 --audit
```

The script writes the continuous kill-switch executions with date, leg, entry/exit time and price, exit reason, pips, EUR P&L, and R to `trades.csv`. It also writes `annual.csv`, `summary.json`, unconstrained trade and control CSVs, and EUR 100 account trade CSVs. All are in this folder. It reads only the listed market files. The run used pandas 3.0.6, numpy 2.5.2, pyarrow 26.0.0, and holidays 0.106. The Exness USD/JPY files have 3,970,582 distinct minute rows spanning 2016-01-03 21:00 to 2026-10-16 20:58 UTC; there were no duplicate timestamps across the three files, no inverted bid/ask opens or closes, and no inverted high/low pairs. There are 130 monthly fix-tick files. The optional Dukascopy `.READY` marker and parquet file were absent at the final check, so no pre-2016 result is claimed.

Holiday shifts are generated with `holidays.Japan()` and the stated year-end closures. There were 755 eligible gotobi dates. One had no eligible long entry and 16 had no eligible tick-based short fill; the full simulation contains 754 longs and 739 shorts. Long entries use the scheduled minute's ask **open**, or the last quote's close if that minute has no tick, with spread at most 5 pips; Sunday reopening is derived from the first Sunday evening bar. Missing-minute time exits use the previous quote's close. Long stop/take hits use bid low/high only *before* the 00:54 exit minute; a same-minute collision is a stop. A gap through a stop gets the worse bar open. The short uses the first tick at or after 00:55:00, no later than 00:55:05, if tick spread is at most 5 pips; subsequent tick asks trigger the stop or close at/after 01:25. No swap or extra slippage is in the baseline.

Position sizing converts the 55-pip stop loss from JPY to USD at the stop USD/JPY price, then to EUR using EUR/USD; realized JPY P&L uses the actual exit USD/JPY and EUR/USD at exit. For 2019 onward EUR/USD is the previous or current minute mid, and for 2016–2018 it is the latest available daily `EURUSD=X` close, an approximation. Annual and continuous headline runs allow fractional sizing so risk is exactly about 6%; the EUR 100 runs apply the requested lot steps. The continuous account starts at EUR 10,000 simply to make its final multiple readable.

## Every year, accounts reset each 1 January

Each cell is **trades / win rate / net pips / account return / maximum drawdown**. A win means net positive pips. Returns compound trade by trade at 6% stop risk, with historical FX conversion; they omit swap and extra slippage. 2026 ends at 16 October. The plain strategy uses the 55-pip stop and timed exit but no take-profit or short. These annual runs do not apply the kill switch, so they measure the rule itself.

| Year | Plain long | Full strategy | Short only |
|---|---:|---:|---:|
| 2016 | 70 / 53% / +384 / +37.6% / 21.7% | 138 / 57% / +372 / +42.4% / 20.4% | 68 / 54% / +128 / +13.8% / 6.5% |
| 2017 | 70 / 59% / +259 / +25.5% / 11.6% | 140 / 61% / +347 / +40.6% / 16.5% | 70 / 60% / +173 / +20.4% / 3.8% |
| 2018 | 70 / 56% / +54 / +3.5% / 11.8% | 138 / 54% / +164 / +16.3% / 12.3% | 68 / 50% / -40 / -4.5% / 11.3% |
| 2019 | 69 / 59% / +225 / +26.1% / 13.2% | 137 / 54% / +314 / +38.6% / 10.3% | 68 / 49% / +77 / +8.7% / 4.0% |
| 2020 | 69 / 58% / +26 / +0.9% / 21.5% | 137 / 59% / +165 / +17.1% / 19.9% | 68 / 60% / +116 / +13.2% / 3.9% |
| 2021 | 70 / 56% / +305 / +38.1% / 5.0% | 140 / 58% / +349 / +44.7% / 7.4% | 70 / 60% / +46 / +5.0% / 5.1% |
| 2022 | 71 / 63% / +583 / +79.6% / 14.7% | 135 / 70% / +887 / +152.7% / 14.6% | 64 / 70% / +271 / +33.8% / 5.4% |
| 2023 | 70 / 57% / +277 / +28.1% / 17.8% | 140 / 61% / +359 / +40.8% / 16.6% | 70 / 60% / +123 / +13.5% / 9.6% |
| 2024 | 70 / 53% / +52 / +0.2% / 32.8% | 140 / 61% / +510 / +66.5% / 22.6% | 70 / 63% / +359 / +46.6% / 7.3% |
| 2025 | 69 / 54% / +444 / +49.3% / 30.0% | 137 / 64% / +574 / +78.3% / 34.5% | 68 / 65% / +297 / +37.0% / 10.3% |
| 2026* | 56 / 59% / +362 / +44.2% / 15.9% | 111 / 56% / +545 / +75.9% / 12.4% | 55 / 47% / +56 / +5.8% / 9.6% |

The 30-pip take-profit by itself barely improved the long: 2,979 versus 2,972 pips across the sample. In the full run, 202 longs hit take-profit, 57 hit the stop, and 495 exited by time. The short stopped once and exited by time 738 times; its apparent win frequency is not protection against an occasional larger loss.

## Continuous account and EUR 100 accounts

The continuous, exact-size account starts 2016-01-01 and includes the specified kill switch. These multiples are *mechanical backtest numbers*, not scalable return forecasts: a 102-fold result would require rapidly growing lots with no broker size, margin, liquidity, or market-impact limit, and it ignores swap.

| Stop risk | Final multiple | Max drawdown | Kill switch |
|---:|---:|---:|---|
| 3% | 11.01× | 18.6% | Never |
| 6% | 101.65× | 34.5% | Never |
| 10% | 315.00× | 50.5% | 2025-10-15 00:54 UTC, drawdown; no later trades |

At 6%, the rolling 60-long sum never crossed -6R in the realized sequence. The 10% result is frozen after the kill switch and is **not** an October 2026 mark-to-market return.

The next table starts with EUR 100, applies the 6% stop-risk ceiling and the 50%/60-long kill switch, and has no deposits or withdrawals. Standard uses 1,000 USD unit steps and minimum (0.01 standard lot); Cent uses 10 USD unit steps and minimum (0.01 cent lot). P&L is converted at each exit.

| Start | Account | Final EUR | Max drawdown | Trades | October 2026 P&L (trades) |
|---|---|---:|---:|---:|---:|
| 2025-01-01 | Standard | 249.24 | 28.1% | 248 | -12.58 (6) |
| 2025-01-01 | Standard Cent | 312.96 | 34.4% | 248 | -17.78 (6) |
| 2026-01-01 | Standard | 161.01 | 10.6% | 111 | -7.97 (6) |
| 2026-01-01 | Standard Cent | 175.72 | 12.4% | 111 | -9.95 (6) |

No small-account run triggered the kill switch. Standard's coarse lot step often takes less than 6% risk and explains much of its lower return. For context, a EUR 100 Standard account opened in January 2025 reached EUR 155.13 at that year's end in this friction-free model. That figure is **not** a live expectation.

## Edge and robustness

`R` is pips divided by the 55-pip intended stop. The table's t-statistics and trade bootstraps are descriptive, not a correction for searching about 108 variants. A day-block bootstrap resamples complete gotobi days to keep the two legs together.

| Rule | Trades | Mean R | t-stat | 95% trade bootstrap mean R | Longest losing streak |
|---|---:|---:|---:|---:|---:|
| Plain long | 754 | +0.0717 | 3.42 | +0.031 to +0.114 | 8 |
| Full | 1,493 | +0.0558 | 6.03 | +0.038 to +0.073 | 7 |
| Short only | 739 | +0.0395 | 4.70 | +0.023 to +0.056 | 8 |

The day-block 95% interval for full mean R was +0.037 to +0.074. This remains positive with same-day long/short dependence. The selected matched control sample draws non-gotobi Japanese business dates from the same years and weekdays with seed 12055. Gotobi shifts crowd Fridays, so there are too few *distinct* non-gotobi Fridays for exact one-for-one matching; the controls contain 644 dates and 1,278 trades versus 754 traded gotobi dates and 1,493 trades. Full control mean was **-0.0040R** (long -0.0091R, short +0.0010R); its day-block 95% interval was -0.024 to +0.015R. The control is informative but cannot rule out all calendar confounds.

| Period | Plain long mean R / pips | Full mean R / pips | Short mean R / pips |
|---|---:|---:|---:|
| First chronological half of each rule | +0.0477 / +989 | +0.0335 / +1,375 | +0.0208 / +422 |
| Second half | +0.0956 / +1,983 | +0.0781 / +3,209 | +0.0582 / +1,184 |
| 2016–2021 selection period | +0.0545 / +1,254 | +0.0375 / +1,710 | +0.0220 / +499 |
| 2022–2026 holdout | +0.0930 / +1,718 | +0.0788 / +2,874 | +0.0615 / +1,107 |

The holdout is stronger, which argues against a purely in-sample accident. It does not remove live execution risk or make the 108-trial choice of take-profit and short independent evidence. The long before the fix is the better-supported component. The chosen take-profit is nearly neutral in aggregate.

**Additional execution cost**, subtracted once per round trip from *every* trade, on top of recorded spread:

| Extra pips/trade | Full net pips | Mean R/trade |
|---:|---:|---:|
| 0 | +4,585 | +0.0558 |
| 0.5 | +3,838 | +0.0467 |
| 1 | +3,092 | +0.0376 |
| 2 | +1,599 | +0.0195 |

**Short fill timing**, using the first tick at/after the target time and the same ask-based exit/stop logic:

| Sell target | Shorts | Net pips | Mean R |
|---|---:|---:|---:|
| 00:55:00 baseline, filled by :05 | 739 | +1,606 | +0.0395 |
| 2 seconds late, still filled by :05 | 736 | +1,265 | +0.0312 |
| 5 seconds late, still filled by :05 | 83 | +125 | +0.0273 |
| 10 seconds late, hypothetical; bot would skip | 742 | +1,027 | +0.0252 |

The five-second row is limited to ticks timestamped exactly within the deadline; most dates have no eligible tick after deliberately waiting until :05. The 10-second row is a sensitivity to delay, **not an executable bot result**. Tick timestamps have subsecond precision in places. These tick prints are quotes, not proof that an order of the required size would fill at the displayed bid/ask.

**Swap:** The price files contain none and I could not obtain a usable history of USD/JPY Standard long swap rates. [Exness says](https://get.exness.help/hc/en-us/articles/360014709151-About-swap) weekday rollover is at 21:00 UTC in summer or 22:00 in winter and forex has a Wednesday triple rate. Approximately 496–500 of the 754 longs survived a weekday rollover (depending on 21:00 versus 22:00), about 72 of them on Wednesday. The official [USD/JPY page](https://www.exness.com/forex/usdjpy/) exposes current trading conditions but did not provide a historical rate series. Positive or negative swap could materially change these returns. At 2 extra pips per trade, another 2.12 pips *averaged over all longs* would erase the sample's remaining pips; at zero extra cost, the corresponding threshold is 6.08 pips/long. Wednesday triples and broker changes make a single assumed rate unreliable.

The maximum observed losing streaks were 7 full-rule trades and 8 in each isolated leg. A 10,000-path Monte Carlo that resamples complete historical trade days at 6% exact fractional risk (no kill switch) estimated a **0.89%** chance of a 50% drawdown over a history-length path; its 5th/median/95th maximum drawdowns were 20.8%/29.0%/42.6%. This is a *conditional* calculation that assumes the observed edge and day distribution persist. It does not model regime change, failed execution, adverse swap, or broker failure, so it understates the practical risk of losing half an EUR 100 account.

## Self-audit, limits, and practical verdict

- The code sorts and de-duplicates bars before sampling. Holiday moves are backward only; no 31st rule is used. Prices at a scheduled minute are that minute's **open**, not its future close; missing-minute prices use the last past close. Stops and takes use contemporaneous high/low only before the timed exit minute, with adverse tie handling. The short's baseline deadline is enforced on actual ticks. A synthetic timing check confirmed that a later high/low within 00:54 cannot override the scheduled 00:54 open exit. This avoids the obvious timestamp and bid/ask look-ahead errors.
- Minute bars do not reveal the order of stop and take touches or whether a stop filled at its quoted level. The stop-first assumption is conservative for collisions, but non-open intraminute price gaps can still cause more loss than modeled. The long entry, stop, and take are not backed by full overnight tick data. No order-book depth, rejects, latency distribution, margin regime, broker volume cap, or changing contract specifications are modeled.
- The five-pip spread gate observes an entry quote. A real market order may fill worse. The short sells at the fix with tick data, but a bot sent at 00:54:59 may execute before or after the exact target; this is not verified. The assumption that the server orders survive outages and rollovers is also unverified.
- The control selection cannot fully match Friday counts and is one random draw. The 2016–2021 rules were selected among about 108 variants, so the nominal t-statistics overstate discovery evidence. The pre-2019 EUR conversion uses daily closes, not minute rates. Historical swap and real fill quality are the two largest missing inputs.
- The Dukascopy file was not ready. Once its `.READY` marker appears, the same script can run with `--data data/dukascopy/USDJPY_2006_2015_m1.parquet --start 2006-01-01 --end 2015-12-31 --audit`. Since no pre-2016 fix ticks were supplied, it uses a clearly approximate 00:55 minute-open short and cannot validate the five-second rule. Inspect file coverage, duplicates, quote sanity, and provider spread differences before interpreting that separate period.

**What is most likely to fail with real money:** a few pips of slippage around the Tokyo fix, missed or delayed fills, and unmeasured rollover swap. The short contributes less than 2.2 pips per trade and was selected after a broad search; I would not count it as durable profit until a live execution log confirms it. The plain overnight long has better evidence, but even it can suffer long losing spells and large equity drawdowns at 6% risk.

For an **EUR 100 account over one year**, a conservative planning estimate is roughly **EUR 90–130**, with outcomes well below EUR 90 possible. This is a judgment that discounts the backtest for missing costs and execution, not a statistical forecast. The friction-free 2025 Standard result of EUR 155 and the spectacular continuous multiples should not be used as expected returns. The strongest actionable conclusion is to obtain account-specific swap history and several months of timestamped live/demo order fills before putting weight on this backtest.
