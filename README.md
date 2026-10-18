# gotobi-fx-bot

Research into retail FX and gold trading strategies on real broker tick data, and the one effect that
survived: an automated **Gotobi USD/JPY bot** for MetaTrader 5.

> **Not financial advice.** This is research code. Trading leveraged CFDs/FX can lose more than you expect;
> past results, including every number below, do not predict future results. Run it on a demo account first.

## What's in the repo

| Path | What it is |
|---|---|
| `src/` | Backtests on Exness bid/ask tick data: liquidity sweeps, ICT order blocks, order flow, 5-minute rules, session drift, trend following, into-the-close momentum, Gotobi |
| `results/` | Reports and trade lists from those backtests |
| `bot/` | The Gotobi bot: calendar, sizing, MT5 broker wrapper, engine, journal, CLI, MT5 simulator, replay |
| `tests/` | 162 fast tests + 2016-2026 replays + a 24/7 soak test + a check that the tests catch mistakes |
| `codex_audit/` | Independent reviews by a second AI agent: the strategy rebuilt from scratch, and three rounds on the bot's code |
| `BOT_README.md` | How to connect an MT5 account and run the bot unattended (demo first) |
| `install_autostart.ps1` | Starts the bot at Windows log-on (Task Scheduler, no time limit; `-TaskName` per account) |
| `.github/workflows/host.yml`, `ci/` | Free hosting on GitHub's Windows machines: the bot runs around each trade, so the PC can be off |

## The finding

Almost everything failed once real spreads and out-of-sample checks were applied (see the research log
below). One effect held up: Japanese importers settle dollar invoices on *gotobi* days (the 5th, 10th, 15th,
20th, 25th and 30th), and banks buy USD into the 09:55 Tokyo fix.

| USD/JPY, buy 15:55 UTC the day before, sell at the fix, 55-pip stop (2016-2026) | Gotobi days | Other days |
|---|---|---|
| Average trade after real Exness spread | +3.7 pips (t 3.2) | -2.5 pips |
| Win rate / profit factor | 57% / 1.40 | 46% / 0.79 |
| Profitable years | 10 of 11 | - |

Gotobi beats control days by 6.5 pips (t 4.6), including in 2016-2018, years the original claim never used.

## The bot

Two trades per gotobi day, never open at the same time:
- **The long.** Buys at 15:55 UTC with a 55-pip stop and a +30-pip take-profit held on the broker's server.
  If neither is hit, it sells at 00:54 UTC, one minute before the fix (exits after the fix give the edge back).
- **The post-fix short.** Sells one second before 09:55:00 JST and buys back 30 minutes later, when the
  importers' dollar buying has stopped. The PC clock is corrected against internet time servers for it.

It skips Japanese holidays and FX-market closures, sizes by risk, survives crashes and outages, and measures the
broker's clock offset. It refuses real-money accounts unless unlocked with two separate keys. See `BOT_README.md`.

Why only these two add-ons: 108 variants were tested, each chosen on 2016-2021 and judged once on 2022-2026
(see "What improves the bot?" below). Only these two improved both periods. All EMA filters, news-day skips,
ATR and trailing stops, and day-type and regime filters failed.

Verification on 2016-2026 Exness data:
- **Matches the research trade for trade.** The plain long reproduces the research backtest (757/757). With
  the take-profit and the short, all 752 longs and 737/739 shorts match the lab that selected them.
- **Robust to crashes and outages.** Over 4,000 random crash-restarts change nothing, and forced outages never
  duplicate or strand a trade.
- **No look-ahead.** Deleting all future prices at the decision moments changes no decision.
- **Runs 24/7.** A soak test drives the real entry point through 5.5 months of prices with disconnects,
  exceptions, dead time servers and 12 kill-and-restarts. The loop never dies, no trade is duplicated or left
  open, and every difference from a fault-free run traces back to a fault at that trade's entry or exit.
- **Independently reviewed.** A second agent reviewed the code three times (`codex_audit/bot_review/REPORT*.md`).
  Each safety problem it found is fixed and has a regression test. They included:
  - an account switched to real money while the bot runs;
  - lost, queued or partly filled orders that could become a second, overlapping trade;
  - the short's deadline checked on a stale clock;
  - other robots' or manual positions;
  - drawdown while flat;
  - damaged state files;
  - an unchecked PC clock;
  - trades dropping out of the kill switch's count.
- **The tests notice mistakes.** On a throwaway copy of the bot, each of 68 deliberate one-line mistakes makes a
  test fail. The real code is never touched.

Not yet verified: a real MT5 terminal, real fills at the fix, and swap. That is what the demo is for.

```
pip install -r requirements-bot.txt
python -m pytest -m "not slow"      # 162 tests, no data needed
python -m pytest                    # + 2016-2026 replays and the soak test (needs the Exness data, src/fetch_exness.py)
python tests/mutation_check.py      # on a throwaway copy: 68 one-line mistakes, each must fail a test
```

Market data is not included: `src/fetch_exness.py` rebuilds it from Exness's public tick archive.

---

# Research log

## 1. Liquidity-sweep reversal backtest (forex + gold)

**Verdict: no tradeable edge.** Across 4 instruments, 2 sweep models, 2 price-action
confirmations, 4 targets and a trend filter (192 variants, ~62,500 trades, Jan 2019 â€“ Sep 2026),
the average trade is **âˆ’0.10R after spread** and **+0.01R before spread**. The sweep-and-reverse
pattern is real enough to look convincing on a chart, but statistically it is a coin flip
that pays the spread every time.

## The strategy that was tested

The common retail/ICT "liquidity sweep" model, made fully mechanical:

1. **Liquidity pool**
   - `asia`: Asian-session high/low (00:00â€“07:00 London time). Trade window 07:00â€“10:00, flat by 16:00.
   - `pdhl`: previous day's high/low. Trade window 07:00â€“16:00, flat by 20:00.
2. **Sweep**: the bid trades through the level inside the window (price must start the window inside the range).
3. **Price-action confirmation** on 5-minute bid candles
   - `reclaim`: a candle closes back inside the level (failed breakout / stop hunt)
   - `mss`: market-structure shift: a close beyond the low (high) of the 6 candles before the sweep extreme
4. **Entry** at the next minute's open. **Stop** beyond the sweep extreme plus one spread.
   **Target**: 1R, 2R, 3R, or the opposite side of the pool (`range`).
5. Optional **trend filter**: only take sweeps with / against the daily trend (prior close vs 20-day SMA).
6. One trade per day; stops under 3Ã— spread are skipped (otherwise costs dominate).

## Data and fill realism

- **Exness public tick archive** (`ticks.ex2archive.com`), Standard-account symbols
  (`EURUSDm`, `GBPUSDm`, `USDJPYm`, `XAUUSDm`): real broker bid **and** ask, rebuilt into 1-minute bars.
  Median spread: EURUSD 1.0 pip, gold $0.16.
- Shorts sell the bid and cover on the ask; longs the reverse. Stops gap to the bar open when
  price opens through them. If one minute touches both stop and target, the **stop wins**.
- No swap (always flat same day). No commission (Standard account is spread-only).
- **In-sample** 2019â€“2023 for choosing; **out-of-sample** 2024 â€“ Sep 2026 for judging.

## Results

Pooled per instrument (every variant):

| symbol | avg R after spread | avg R before spread | spread cost per trade |
|---|---|---|---|
| EURUSD | âˆ’0.080 | +0.037 | 0.117 R |
| GBPUSD | âˆ’0.090 | +0.016 | 0.107 R |
| USDJPY | âˆ’0.137 | âˆ’0.026 | 0.111 R |
| XAUUSD | âˆ’0.088 | +0.005 | 0.093 R |

- Only **9 of 192** variants were profitable in-sample, which is fewer than chance would produce.
- The in-sample winner (gold Â· PDH/PDL Â· reclaim Â· 3R Â· with-trend: +0.10R, PF 1.16, t = 1.0)
  went **+0.03R, PF 1.04** out-of-sample. That's break-even.
- The best-looking out-of-sample line (gold Â· PDH/PDL Â· reclaim Â· range target: +0.44R, PF 1.58)
  is **five trades**. Its biggest winner, +66R, came from the 29 Jan 2026 gold crash, entered with a $6 stop.
  Remove the top 5 trades and the 2024â€“26 total goes from +128R to **âˆ’26R**. It was ~0R in-sample.
- Every confirmation type, target and trend filter lands in the same âˆ’0.25R to +0.10R band.
  Changing the rules only reshuffles the noise.

Full table (no trend filter): [`results/base_table.md`](results/base_table.md).
All 192 variants with IS/OOS stats: [`results/grid.csv`](results/grid.csv).

### The one real signal

Gold sweeps of the **previous day's high/low with a reclaim close** show a small gross edge
(about +0.06 to +0.26R before costs depending on target, 2019â€“2026). After the Standard-account spread it's ~0.
That's the only place worth further work, e.g. on a Raw/Zero account where cost per trade is
lower. Even then it's fragile: it swings âˆ’16R to +21R from year to year.

## Reproduce

```bash
python src/fetch_exness.py XAUUSDm 2019 2026 9   # also EURUSDm GBPUSDm USDJPYm
cd src && python run_grid.py                      # ~6 min on 4 cores
```

## Multi-signal "safe" version: $1,000 over the last 3 years

`src/confluence.py` tags every sweep + reclaim signal with 7 confluence checks (trend on 20 & 50-day SMA,
quick reclaim, shallow sweep, strong rejection candle, structure break, room to target, sane stop size)
and simulates 6 exit plans. `src/select_rules.py` searched 5,760 combinations of instrument Ã— model Ã— up to
3 signals Ã— exit **using only Jan 2019 â€“ Sep 2023**. The winner:

> **Gold, previous-day high/low sweep, reclaim close + trend agrees + reclaim within 3 candles + sweep
> â‰¤ 0.25Ã— daily ATR deep, stop beyond the wick, 3R target, 1% risk.**

`src/final_run.py` ran it once on the untouched **Oct 2023 â€“ Sep 2026**, with $1,000, 0.01-lot sizing and the Exness Standard spread:

| | end balance | max drawdown |
|---|---|---|
| spread only | **$1,140** | 9% |
| + $0.10/oz slippage | $1,133 | 9% |
| + $0.20/oz slippage | $1,094 | 9% |

99 trades (33/yr), 31% win rate, +0.12R per trade, worst losing streak 10, 72% longs.
Without its best 5 trades it is âˆ’3.3R. Bootstrap of the same trades: 27% chance of ending below $1,000.
The top 20 selection-period rules averaged +0.21R before the cut and **âˆ’0.01R** after it,
so most of the search was fitting noise. Treat the $1,140 as a small, unproven edge, not a reliable one.

## Order blocks, order flow and liquidity heat map

`src/ict.py` adds the full ICT-style sequence: sweep â†’ market-structure shift â†’ **order-block limit entry at the
50% mean threshold** (with a market entry at the shift recorded for comparison). It also adds:
- **fair-value-gap** check on the displacement leg
- **order flow** from tick-rule delta on the Exness mid price (spot FX/gold has no exchange volume, so tick delta is the standard proxy):
  tick-volume spike on the sweep candle, absorption (delta leaning into the sweep), aggressive delta on the shift candle
- **liquidity heat map**: number of untouched M15 swing stops from the last week cleared by the sweep, plus untouched opposite
  liquidity between entry and the 3R target

`src/select_ict.py` searched 15,600 combinations on Jan 2019 â€“ Sep 2023 only, then ran the winner once on Oct 2023 â€“ Sep 2026.

| finding (selection period, all symbols, 3R) | avg R |
|---|---|
| order-block **limit** entry | **âˆ’0.176R** (22% win) |
| market entry at the structure shift | âˆ’0.048R (34% win) |
| absorption signal on / off | âˆ’0.111 / âˆ’0.035 |
| heat-map signal (â‰¥2 stop layers swept) on / off | âˆ’0.069 / âˆ’0.020 |

The order-block limit entry is the worst way to enter. A pullback fill tends to arrive on exactly the trades that are about to fail, and the good
trades leave without you. None of the order-flow or heat-map signals moves the result into profit.

**Winner (EURUSD, Asia sweep, FVG + tick-volume spike + heat, 2R): $1,000 â†’ $941 over the last 3 years.**
The top 20 rules from the selection period averaged +0.17R before the cut and âˆ’0.05R after it.
The best result in this project is still the simpler gold previous-day-high/low rule above ($1,000 â†’ $1,140).

## Gold-only R&D: win rate, exit management, every cost and tax

`src/gold_rnd.py` added 16 entry filters (trend, quick reclaim, strong candle, shallow sweep, London-open / NY session,
mid-week, skip NFP Fridays, high-volatility regime, premium/discount, vs daily open, stacked Asia + PDH sweep,
tight Asian range, previous-day direction...) and 13 exit plans (fixed 1â€“4R, break-even at 1R, half off at 1R with
runner, trailing stops). Costs: real Exness spread in the fills, plus $0.10/oz slippage per trade; the Raw Spread account
adds $3.50/side/lot commission. Swap is zero because every trade is flat before the daily rollover.
`src/gold_select.py` required a rule to be profitable in **both halves** of 2019â€“Sep 2023 before ranking it.

- 34,567 rules had â‰¥100 trades; 1,284 passed the both-halves check. Their top 20: +0.23R / 44% win before â†’ **âˆ’0.06R / 35% win** in the last 3 years.
  This round's winner (MSS entry, trend + skip NFP + high-vol, 4R): $1,000 â†’ **$976**.
- **Win rate vs edge.** On the best rule (PDH/PDL reclaim + trend + quick + shallow), the only profitable plan is the 3R target at a
  31% win rate. Taking half off at 1R lifts the win rate to 44%, but the 3-year result drops from $1,133 to $992.
  The edge, such as it is, sits in the few trades that run to 3R.
- **Costs per trade** at 1% risk on $1,000 (median 0.02 lots, $3.41 stop): spread â‰ˆ $0.48, slippage â‰ˆ $0.20, commission $0, swap $0.
  That's ~0.10R per trade, about the size of the whole edge.
- **Raw Spread vs Standard:** same rule, last 3 years: Standard $1,133, Raw $1,056. Raw's cheaper spread is offset by its commission,
  and its slightly different price feed changes which trades trigger. The result swinging that much on a feed change is itself a warning sign.
- **Irish CGT (33% above the â‚¬1,270 annual exemption, losses carried forward):** gains of $50â€“130 a year on $1,000 sit
  far under the exemption, so tax is â‚¬0. Tax only matters once yearly profit passes about â‚¬1,270.

## The 60%-win-rate search (gold)

**Pullback buying** (`src/high_wr.py`, `src/eval_high_wr.py`; Connors RSI-2 and N-day-low pullbacks, daily bars, real swap assumed):
the high win rate is robust, 60â€“72% in every period from 2015 to 2026, but the profit isn't. The chosen rule went
+0.09R â†’ +0.01R (last 3y) â†’ âˆ’0.12R (2015â€“18), and in the last 3 years it was no better than random entries with the same holding time (p = 0.54).

**Asian-session drift** (`src/asia_drift.py`): most of gold's gains since 2015 came between 18:00 and 03:00 New York time
(positive in 10 of 12 years, +6.8% in 2015 while gold fell). Trading it every night pays the spread twice, which ate the
drift until spreads compressed (0.04% of price in 2016 â†’ 0.006% in 2026). Buy at 18:00 NY and sell at 03:00 NY: no swap, since it never crosses the rollover.

The only rule with â‰¥60% win rate that was profitable in both halves of 2019â€“Sep 2023:

> **Gold Asia Night:** on evenings when the New York session (08:00â€“17:00) closed **down** and daily ATR is **above its
> 100-day median**, buy at 18:00 NY. Take profit +0.15Ã— daily ATR, stop âˆ’0.30Ã— daily ATR, else sell at 03:00 NY. 1% risk.

| period | trades | win rate | avg R | $1,000 becomes (spread, $0.10 slippage, Irish CGT) | max DD |
|---|---|---|---|---|---|
| 2019 â€“ Sep 2023 (selection) | 225 | 62% | +0.014 | $1,028 | 11% |
| **Oct 2023 â€“ Sep 2026 (last 3 years)** | 170 | **74%** | +0.138 | **$1,260** | 4% |
| 2015 â€“ 2018 (never used) | 119 | 61% | âˆ’0.042 | $949 | 8% |

By year (avg R): 2016 âˆ’0.22, 2017â€“2019 â‰ˆ 0, 2020 +0.04, 2021 +0.19, 2022 âˆ’0.14, 2023 +0.17, 2024 +0.13, 2025 +0.12, 2026 +0.12.
The win rate holds in every regime. The profit shows up only when gold trends up and spreads are tight, as they have been since 2023.
Adding a trend filter did not rescue the bad years.

## EUR 100, 5-minute timeframe, up to 10% risk per trade

**5-minute signal lab** (`src/m5_lab.py`, `src/m5_select.py`): RSI(3) and Bollinger mean reversion, hour-of-day entries
and New York opening-range breakouts, each with session/trend filters and ATR-based TP/SL/time exits (2,682 rules).
1,853 rules won â‰¥60% of trades in 2019â€“23, but only 4 of them were profitable even at today's spread, none in both halves, and all
four lost money in the last 3 years and in 2016â€“18. On 5-minute gold, a small high-win-rate target is roughly 25% eaten by spread + slippage.

**Gold Asia Night holds up and is the only candidate.** Re-priced at today's spread (0.007% of price):
2016â€“18 +0.08R (64% win), 2019â€“Sep 2023 +0.04R (62%), last 3 years +0.15R (74%), positive in 9 of 11 years.
Its earlier losses were a spread problem, not a signal problem. Run on 5-minute candles it gives the same result (74% win, +0.138R in the last 3 years).

**Sizing** (`src/sizing.py`, `src/killswitch.py`):

| | 2% risk | 5% risk | **10% risk** |
|---|---|---|---|
| EUR 100, last 3 years, real costs (Cent account) | EUR 158 | EUR 298 | **EUR 755** (max DD 36%) |
| EUR 100, 2016â€“2026 in order, real spreads, with kill switch | â€“ | EUR 225 | EUR 376 (max DD 64%) |
| Monte Carlo 3y median, "typical" edge (2016â€“26, today's spread) | EUR 128 | EUR 176 | EUR 269 (10% chance < EUR 100) |
| Monte Carlo 3y median, bad regime (2016 + 2022 trades) | EUR 72 | EUR 42 | **EUR 15** (64% chance < EUR 20) |

- Kelly-optimal risk: 32% (last 3y), 20% (typical), 0% (bad years). 10% is about half-Kelly on the typical estimate. That's aggressive, and only
  defensible with the **kill switch**: trade real money only while the last 30 signals show â‰¥60% wins and positive total R.
- **Broker constraint:** today the stop is 0.3 Ã— ~$140 daily ATR â‰ˆ $42/oz. Exness Standard's 0.01-lot minimum (1 oz) would risk ~36% of EUR 100,
  so it can't be sized. The **Standard Cent** account trades 0.01 oz with identical gold spreads (checked month by month, Oct 2023 â€“ Sep 2026).
  10% risk = 0.28 oz â‰ˆ 11Ã— leverage, inside even the EU 1:20 cap.
- **Costs per trade:** spread ~$0.16â€“0.50/oz at 18:00 NY, $0.10/oz slippage assumed, no commission, **no swap** (out before the rollover).
- **Tax (Ireland):** 33% CGT only above EUR 1,270 of yearly gains. Every simulated year at EUR 100 stays under it, so tax is EUR 0.

## Should EUR 100 go in? Walk-forward verdict (`src/asia_v2.py`)

Improvement attempts on Gold Asia Night: 4 entry times x 5 exit times x 5 targets x 3 stops x 64 filter sets
(19,200 rules), real Exness bid/ask, 2016-06 -> 2026-09, 2,596 nights.

- **Walk-forward** (rule re-chosen each January on earlier nights only, traded blind next year), 2018-2026:
  419 trades, 74% win, **+0.000R at real costs** (+0.009R at today's spread).
  EUR 100 at 10% risk -> EUR 75 (max DD 76%); at 2% -> EUR 99.
- **v1 is a bull-market effect.** v1 filters with tp 0.15 / sl 0.3, avg R at real costs:

  | entry / exit | 2018 - Sep 2023 | Oct 2023 - Sep 2026 |
  |---|---|---|
  | 18:00 / 03:00 (v1) | +0.012 | +0.138 |
  | 18:05 / 03:00 | -0.018 | +0.096 |
  | 18:30 / 03:00 | -0.046 | +0.066 |
  | 20:00 / 03:00 | -0.090 | +0.062 |

  Every variant was roughly zero or negative before the 2023-26 gold rally.
- **The overnight drift is real but tiny.** Gold earns its intraday return 18:00-03:00 NY
  (+3.0 bp/night, t = 3.1; London and NY sessions ~0), but that is only +0.001R per night at real costs on a 1-ATR stop.
  Trend, NY-down and volatility filters don't improve it reliably.
- The 18:00 reopen minute is not a free edge: +0.4 bp mean move, smaller than the spread; the worst 10% of spreads double in the first 2 minutes.

**Verdict: do not trade real money with this.** Most of the backtested profit is gold's 2023-26 rally, and a leveraged
nightly long adds costs and stop-outs on top of that same exposure. Nothing in this repo is live.

## Published effects with textbook settings (`src/classics.py`)

20+ years of Yahoo daily data, no tuning, Exness CFD spread + overnight financing charged.

| Strategy | Gross | Net (CFD) | Note |
|---|---|---|---|
| Trend following, 12-month momentum, 14 markets, 2005-26 | Sharpe +0.37 | CAGR -3.1% | nightly financing on ~3x notional eats it |
| 50/200 moving-average trend, 14 markets | Sharpe -0.07 | CAGR -5.1% | |
| Turn of the month, S&P 500, 2008-26 (post-publication) | | CAGR +0.8%, Sharpe 0.14 | was Sharpe 0.84 in 1950-89; decayed |
| Overnight S&P 500, 2008-26 | CAGR +7.4% | CAGR -8.9% | two spreads a day + financing |

Unlevered ETFs for comparison, 2005-2026 (USD, monthly):

| Holding | CAGR | Sharpe | Max DD | EUR 100 -> (21 y) | Last 3 y |
|---|---|---|---|---|---|
| S&P 500 | +10.8% | 0.77 | 51% | 938 | 185 |
| Nasdaq 100 | +15.0% | 0.85 | 50% | 2,091 | 201 |
| Gold | +10.5% | 0.66 | 43% | 872 | 223 |
| 60% S&P / 40% gold, monthly rebalance | +11.3% | 0.97 | 29% | 1,029 | 203 |
| S&P with 10-month SMA timing | +8.5% | 0.83 | 22% | 588 | 147 |

Conclusion: no CFD trading rule tested in this repo beats owning the market unlevered after costs.
Caveat: 2005-26 was kind to both stocks and gold. Ireland: UCITS ETF gains pay 38% exit tax (from 2026), deemed disposal every 8 years.

## The one real edge found: DAX into-the-close momentum (`src/close_mom*.py`)

Published effect: Gao, Han, Li & Zhou (2018); Baltussen, Da, Lammers & Martens (2021). Option dealers hedging
their gamma exposure and leveraged ETFs rebalancing push prices in the direction of the day's move into the close.
Rule taken from the papers: signal = previous official close -> 30 min before today's close; buy if up, sell if down;
exit with the last tick before the close; never held overnight (no financing).
Real Exness Standard bid/ask, Aug 2019 - Sep 2026, + 0.2 bp slippage per side.

| Market | Gross per trade | t | Verdict |
|---|---|---|---|
| S&P 500 (US500) | +0.54 bp | 0.65 | gone; negative every year 2024-26 (likely 0DTE options flipped dealer hedging) |
| Dow (US30) | +0.39 bp | 0.49 | gone |
| Nasdaq 100 (USTEC) | +0.58 bp | 0.62 | gone; -1.9 / -3.8 bp in 2024 / 2025 |
| FTSE 100 (UK100) | +1.11 bp | 2.51 | faded: +0.44 bp since 2021 |
| Gold (13:30 settlement) | +0.05 bp | 0.18 | none |
| EURUSD / GBPUSD / USDJPY (London fix) | -0.25 / +0.19 / +0.74 bp | -1.0 / 0.7 / 3.2 | USDJPY real but below the ~1.2 bp cost |
| **DAX (DE30), all days** | **+1.60 bp** | **3.27** | real |
| **DAX, big-move days** (abs(signal) > trailing 250-day median) | **+3.19 bp** | **3.99** | strongest result in this repo |

DAX robustness: positive at every entry time 15-60 min before the close and at every big-day cut-off (30th-70th percentile),
t 2-5; bigger moves -> stronger continuation; works on both up and down days.

Economics. Exness cut index spreads in Sep 2025 (DE30 ~3.3 -> 0.3-0.6 bp, UK100 7.3 -> 0.9-1.5 bp, US500 3.5 -> 0.65 bp).
At the old spread the DAX rule lost money every year. At today's cost (0.67 bp round trip):

| Scenario (DAX big days, ~121 trades/yr) | Net per trade | 3-year EUR 100 at 10x leverage (median) | P(loss) | median max DD |
|---|---|---|---|---|
| optimistic (2019-26 history) | +2.52 bp | 226 | 4% | 24% |
| realistic (2021-26) | +0.85 bp (90% CI -0.32 .. +2.06) | 127 | 26% | 27% |
| pessimistic (2024-26) | +0.54 bp | 113 | 36% | 27% |

Break-even round-trip cost since 2021 is ~1.5 bp (1.2 bp since 2024): with 0.5 bp slippage per side the edge is gone.
2026 so far: -0.4 bp gross. Verdict: a real, mechanism-backed edge, but after today's costs it is small and not
statistically proven in the recent era. Paper-trade it before any real money.

Also tested and rejected here: gold "hat" seasonality (`src/gold_hat.py`): Asia-session long +2.8 bp/day gross (t 2.95)
is mostly gold's trend (lost in 4 of 6 years 2017-22 at today's spread); US-session short ~0.
`classics.py` costs corrected to measured spreads (FX/gold were overcharged 2-4x); conclusions unchanged.

## Gotobi (USD/JPY into the 09:55 JST Tokyo fix): the strongest result (`src/gotobi*.py`)

Rule tested exactly as given: on days ending in 0 or 5 (weekend -> Friday before), buy USD/JPY at 15:55 UTC the day
before, sell at the 09:55 JST fix (00:55 UTC), 55-pip catastrophic stop. Real Exness Standard bid/ask
+ 0.2 bp slippage per side, 2016-01 -> 2026-09. Control = the same window on every other business day.
Mechanism support: Ito & Yamada (J. Int. Econ. 2017) document dollar-biased order flow into the Tokyo fix.

| Window A (the pasted rule) | Gotobi days | Control days | Difference |
|---|---|---|---|
| Net per trade, 2016-2026 | +3.18 pips (t 2.70), win 55%, PF 1.33 | -2.33 pips | +5.33 pips gross, t 3.73 |
| Japanese holidays also moved | +3.71 pips (t 3.18), win 57%, PF 1.40 | -2.52 pips | +6.54, t 4.62 |
| 2016-2018 (never in the claim's backtest) | +2.61 pips, PF 1.23 | -2.09 | +6.97, t 2.44 |
| 2022-2026 (claim: PF 1.36, +21.7%, DD 7%) | +4.24 pips, PF 1.37, +28.3% at 1% risk, DD 6.4% | -2.54 | +4.86, t 1.94 |
| Years profitable | 10 of 11 (2018 flat) | 1-2 of 11 | |

Checks passed: beats control on every weekday (weekday-matched excess +4.8 pips); works without Monday trades;
positive on the 10th/15th/20th/25th (5th and 30th ~flat); post-fix short (09:55 -> 11:00 JST) also works
(+1.59 pips net, t 2.77; vs control t 3.41) and holds in 2016-2018. Pre-fix Tokyo morning alone is too small after costs.
Cost: average spread paid 1.5-2.4 pips per trade (median 1.0-1.1); Cent account USD/JPY spreads identical to Standard.

EUR 100 (window A, pasted dates; real 2016-2026 sequence with Irish CGT / 3-year Monte Carlo):

| Risk per trade | 2016-2026 real | Last 3 years real | 3-yr MC median | P(loss) | P(DD > 50%) | Half-edge MC median |
|---|---|---|---|---|---|---|
| 2% | 227 (DD 12%) | 124 | 125 | 9% | 0% | 111 |
| 5% | 641 (DD 29%) | 158 | 167 | 11% | 2% | 123 |
| 10% | 2,222 (DD 51%) | 199 | 238 | 14% | 37% | 128 |
| A+D split, 10% total | 1,726 (DD 36%) | 234 | 220 | 5% | 2% | 140 |

Full-Kelly risk is ~18% per trade for A alone. 10% risk = 28.6x leverage (EU cap 30:1). Exness Standard's 0.01-lot minimum
= 3% risk on EUR 100; the Cent account sizes freely. Needs automation (exit is 00:55 UTC). Nothing is live.

Gotobi execution timing (window A, net pips per trade, 2016-2026): entry anywhere within +-60 min of 15:55 UTC keeps
+2.3 to +3.7 pips. Exit: 10 min early +2.69, 1 min early +3.03, at the fix +3.18, 1 min late +2.18, 5 min late +1.25,
30 min late -0.03. An automated version should close at ~00:54 UTC (09:54 JST), never after the fix.

### Gotobi on EUR 1,000, 1 Jan -> 16 Oct 2026 (`src/gotobi_2026.py`; trade list in `results/gotobi_2026_trades_1pct.csv`)

Exness Standard, lots rounded down to 0.01, real fills, EUR account. 56 trades.

| Version | 1% risk | 5% risk | 10% risk |
|---|---|---|---|
| Rule as written (weekend -> Friday) | 1,008 (DD 3%) | 1,029 (DD 18%) | 1,014 (DD 35%) |
| Japanese holidays moved (no Tokyo fix on holidays) | 1,039 (DD 3%) | 1,222 (DD 15%) | 1,445 (DD 29%) |
| Split long+short, holiday dates | 1,011 | 1,078 | 1,162 |

The as-written rule traded three Japanese holidays (20 Mar, 5 May, 20 Jul): -55.6, -55.6, -13.9 pips.
The holiday version traded the day before instead: +34.3, +34.1, -1.5. October so far: 3 trades, 2 stops.
Estimated swap would add EUR 11 / 72 / 186 (holiday version, 1/5/10%). Irish CGT: EUR 0 (gains < EUR 1,270).

## Automated Gotobi bot (`bot/`, `tests/`, `BOT_README.md`)

Python bot for MetaTrader 5 (official `MetaTrader5` package): gotobi calendar (weekends, Japanese public and bank
holidays, Christmas/New Year skipped), buy 15:55 UTC with a server-side 55-pip stop, close 00:54 UTC, risk-based
sizing within margin, crash/restart recovery, broker-history double-entry guard, kill switch, single-instance
lock, dry-run, and a two-key lock against real-money accounts.

Verification (91 tests, all passing; `python -m pytest`):
- simulator with the real MT5 package's exact fields/constants (checked against the installed package)
- 2016-2026 replay of the production code reproduces the research backtest trade for trade:
  757/757 (rule as given) and 755/755 (holiday rule), identical entry/exit minutes, prices and exit reasons
- production settings 2016-2026 at 1% risk: 752 trades, 56.6% won, +3.45 pips/trade, EUR 1,000 -> 1,458
- 3,998 random crash-restarts: no trade changes; forced outages: no duplicate or stranded trade
- look-ahead test: with all prices after the decision deleted at 59 moments (entries, exits, mid-trade, Sunday
  reopens) every decision is identical; a planted 3-minute peek is caught
- `tests/mutation_check.py`: 23/23 planted bugs caught; broker clock offset measured automatically (UTC+2/+3 brokers)
Found and fixed by the tests: reopen-wait reset by brief price gaps (now waits 15 min after prices return, as the
backtest did); a feed outage stretching the 2-hour weekday entry limit; state loss after a stop-out could have
allowed a second buy (now blocked by the broker's own deal history).
Not yet verified: a real MT5 terminal (demo period). Stop-outs in 10 years all filled at about -55.6 pips.

## What improves the bot? 108 add-ons tested honestly (`src/gotobi_lab.py`, `gotobi_lab2.py`, `fix_seconds.py`, `gotobi_lab3.py`)

Setup:
- **Universe:** the bot's own 752 trades (2016-2026). The lab reproduces each one to 1e-6 first.
- **Fills:** the simulator's rules.
- **Inputs:** only what is known at decision time (completed candles; Fed and BoJ dates from the official
  calendars, `src/lab_events.py`).
- **Score:** Sharpe of the per-slot result in R. A skipped trade counts as 0, so trading less is not free.
- **Validation:** each idea is chosen on 2016-2021 and judged once on 2022-2026. Walk-forward re-selection runs
  from 2019, and filters are compared with random filters that skip the same number of trades.

Base Sharpe: 0.75 (2016-21), 1.08 (2022-26).

| Family | Best on 2016-21 -> its 2022-26 Sharpe (base 1.08) | Walk-forward 2019-26 (base 1.04) |
|---|---|---|
| EMA filters (H1/H4/D1, EMA 20-200, above/below, stacked, sizing tilts; 28) | 1.05 | 0.66 |
| News days (skip FOMC, FOMC minutes, BoJ, wild/quiet entry days; 8) | 0.80 | 0.89 |
| Stops (fixed 30-150, none, ATR 0.5-2x, breakeven, trailing; 18) | 1.02 ("no stop": worst trade -3.1R) | 1.08 |
| Take-profits (20-80 pips, ATR, half-off; 9) | **1.42** (+30 pips) | **1.26** |
| ATR sizing / equity-curve sizing (4) | 1.00 | 0.96 |
| Extra trades (post-fix short, adds at Tokyo open, re-buy after stop; 13) | **1.39** (post-fix short) | **1.40** |
| Day types (25th/30th, month-end, no Mondays, no moved days; 7) | 0.83 | 0.95 |
| Regimes (ATR rank, 5/20-day moves, 60-day high, carry trend, London surge; 10) | 1.14 | 1.04 |
| Entry time (12:55-23:00 UTC; 7) | 0.03 (17:55 looked best, then collapsed) | 0.80 |
| Exit time (00:30-01:00; 5) | 1.12 (00:55) | 1.05 |

EMA filters skip trades that are better on average than the ones they keep. Fed and BoJ days are not worse for
gotobi, and skipping them lowered the score (random-filter p 0.8-0.99).

Stress tests of the two survivors:
- **Take-profit.** Every level from +20 to +60 pips helps in both periods. It keeps the average (+0.063R) and
  cuts the swings: big spikes into the night tend to give back by the fix.
- **Post-fix short (00:55 -> 01:25 UTC).**
  - +0.031R per trade (t 3.7): 2016-21 t 1.5, 2022-26 t 3.5.
  - The same short on the 1,860 non-gotobi fix days loses (-0.008R; difference t 2.9). It is gotobi flow, not a
    Tokyo-morning habit.
  - Correlation with the long: about zero (-0.02).
- **Together.** Sharpe 0.91 -> 1.53 (paired bootstrap of the gain, 90% CI +0.26 to +1.01). Better than the
  plain long in 10 of 11 years; no losing year.

Raw ticks around the fix (8.2 million, 2016-2026, `data/fix_ticks/`):
- **Gotobi days:** the mid falls 0.7 pips in the 5 seconds after 09:55:00, 1.2 by one minute and 3.5 by 30
  minutes (t about -8 to -10).
- **Control days:** -0.2 to -0.9.
- **Timing of the short (net pips):** landing anywhere from 10 s before to 1 s after 09:55:00 earns +1.55 to
  +1.82; +2 s earns +1.33; +5 s +1.03; +60 s +0.58.
- **Consequence:** the bot sends the sell at -1 s and corrects the PC clock by SNTP. The development PC was 0.84 s
  slow.

Money, $1,000 USD account, production bot code replayed (`python -m bot.replay ... --risk 6 --leverage 500`):

| 6% risk per trade | 2016-2026 | 2025-2026 | 2026 (to 16 Oct) |
|---|---|---|---|
| Plain long (before) | $9,746 (max DD 35%) | $1,923 (DD 31%) | $1,369 (DD 16%) |
| Long + take-profit + post-fix short | **$42,665 (DD 37%)** | **$2,603 (DD 36%)** | **$1,607 (DD 13%)** |
| ... if every short fills 0.5 pip worse | about $30,400 (DD 38%) | about $2,370 | about $1,550 |

With the new rule every year 2016-2026 is positive (+9% in 2018 is the worst; 2026 to date +63%).

Monte Carlo over 3 years (0.5-pip short haircut):

| Risk | Median growth | Chance of a 50% drawdown | ... if the edge is half as good |
|---|---|---|---|
| 5% | x2.3 | 0.1% | 2% |
| 6% | x2.6 | 0.8% | 6% |
| 7% | x3.1 | 2.2% | 12% |
| 8% | x3.5 | 5% | 19% |
| 10% | x4.5 | 16% | 40% |

At 10% the 50% kill switch would have stopped the bot in September 2025. **6% is the setting.**

Euro accounts, production code, 6% risk (`src/eur_accounts.py`):
- **EUR 1,000 from 1 Jan 2026:** EUR 1,611.60 (+61%, max DD 13%). The plain long would have made EUR 1,375.42.
- **EUR 100 from 1 Jan 2025, Standard account:** EUR 224.42 (+124%, DD 31%). The minimum 0.01 lot makes the risk
  per trade 3-6%; the plain long would have made EUR 168.29.
- **EUR 100 from 1 Jan 2025, Cent account** (exact sizing): EUR 265.40 (DD 37%).
- **EUR 100 from 1 Jan 2026 (to 16 Oct):** Standard EUR 146.11 (+46%, DD 11%), Cent EUR 162.74 (+63%, DD 13%).
  The plain long would have made EUR 132.75 and EUR 138.71.
- **Each year on its own** (fresh EUR 100 every 1 Jan, compounding within the year; Cent / Standard): 2023 EUR 129
  / 108, 2024 EUR 153 / 137, 2025 EUR 163 / 145, 2026 to 16 Oct EUR 163 / 146. Worst in-year drawdown 37% (2025).
- **Independent audit** (`codex_audit/`): Codex re-implemented the rule from the spec and the raw data alone. It
  found the same trades and called it a "weak or fragile edge": real on gotobi days (t 6.0, control days flat),
  but only about 3 pips per trade, with overnight swap and the fix-second fill unmodelled.
