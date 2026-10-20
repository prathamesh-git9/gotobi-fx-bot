# Backtest Fabio Valentini's NASDAQ scalping model (YouTube, Chart Fanatics, 21 Sep 2025) and try to make it profitable

Video: "Trading LIVE with a World TOP Ranked Scalper (EXTREME Accuracy)", https://youtu.be/tvERE-Beu2U (Fabio Valentini,
claims an audited 218% return in the Robbins World Cup, futures). The model is explained in
transcript_model_chapters.txt (minutes 0-48; full transcript incl. live trading in transcript_full.txt). Read it
first and extract the rules yourself. Work only in this folder; do not read other code or results in this repository
except the data listed below.

In short (verify against the transcript): two models, both built on auction market theory and the volume profile.
1. Trend model, New York session only, NASDAQ (NQ) / S&P (ES): market must be OUT OF BALANCE (left the previous day's
   value area / profile); location = the low-volume node (LVN) of the impulse leg (profile from swing point A to B);
   trigger = aggression (big trades, e.g. >= 30 contracts in a minute on NQ) at the LVN; stop just beyond that
   aggression (or 1-2 ticks inside the swing high/low); target = the POC of the previous balance area; whole
   position off at the target; move the stop to break-even quickly (CVD pushing / an additional breakout); no
   overnight holds; risk 0.25-0.5% per trade.
2. Mean-reversion model, London session (and compressed summer months): market IN BALANCE (previous day's profile);
   ignore the first breakout out of balance; when price comes back inside, take the SECOND swing on its retracement
   (LVN + aggression), target the POC; stop just beyond the aggression; break-even after an additional breakout.

## Data (read only; UTC 1-minute bars)
- E:/Projects/New folder/liquidity_sweep/data/: USTECm_m1 (NASDAQ 100 CFD), US500m_m1, DE30m_m1 (2019-08..2026-09),
  XAUUSDm_m1 (2019-01..2026-09) + XAUUSDm_2015_m1 (2015-08..2018). Exness Standard bid/ask: bopen bhigh blow bclose
  aopen ahigh alow aclose, plus n (quote ticks in the minute) and up/dn (ticks whose mid rose/fell).
- E:/Projects/New folder/liquidity_sweep/strategies/fabio/data/: NSXUSD_hd_bid_m1, SPXUSD_hd_bid_m1 (HistData NASDAQ
  100 / S&P 500, 2016-01..2019-12, BID only, columns bopen bhigh blow bclose, no volume). Verified: same timestamps
  as Exness (0-minute shift), ~2 bp below the Exness mid. For 2016..2019-07 build the ask as bid + the median Exness
  spread for that New York minute-of-day measured on Aug 2019 - Jul 2020, and splice onto Exness from 2019-08-05.
- Known data facts: Exness US index quotes stop at 15:59 New York on many days in 2019-2023 (do not schedule exits at
  16:00); Exness cut US index spreads from 3-4 bp to ~0.9 bp in Q4 2024 and ~0.4-0.65 bp in Q3 2026.
- There is NO exchange volume, footprint, big-trade or CVD data. Build profiles from time at price (TPO) and/or the
  tick count n as a volume proxy; say which you used. Test any aggression proxy the data allows (tick-count bursts,
  up/dn imbalance) honestly, and also run each model WITHOUT the aggression trigger.

## What to do
1. RULES.md: exact mechanical rules for both models (profile construction, value area 70%, POC, LVN definition,
   out-of-balance test, swing/leg definition, entry, stop, target, break-even rule, sessions incl. DST), written
   BEFORE computing returns. Fabio says step 3 (reading aggression) is discretionary; make the most faithful
   mechanical version you can and say what is lost.
2. research.py: backtest on NASDAQ (main), S&P, and as a check DAX and gold. Buy at the ask, sell at the bid,
   next-bar entries, stop wins ties inside a bar, intraday only. Choose free parameters on 2016-2021 only, judge
   once on 2022-2026, compare with the same entries in a random direction (seeded), Bonferroni across rules.
3. Make it profitable, honestly: propose and test improvements (filters, exits, sessions, risk) chosen ONLY on
   2016-2021 data, then judge once on the hold-out. Report the hold-out even if it is negative.
4. REPORT.md: for every rule and improvement report (a) the last 10 years 2016-10-01..2026-09-30, (b) the last 2 years
   2024-10-01..2026-09-30 and (c) this year 2026-01-01..2026-09-30: trades, avg R, t, win rate, EUR 1,000 compounded at
   0.5% risk per trade (Fabio's) and at 2% (final balance, max drawdown). Finish with an honest verdict: does the
   model work on these markets, what part of his edge cannot be tested without order-flow data, and the single best
   version (if any) with how confident you are.

Memory: about 4 GB free and other backtests may run at the same time. Load only needed columns, one symbol at a time,
free frames with del + gc.collect().
