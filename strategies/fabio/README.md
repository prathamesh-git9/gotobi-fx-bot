# Fabio Valentini's NASDAQ scalping model, tested

**Video:** "Trading LIVE with a World TOP Ranked Scalper (EXTREME Accuracy)", Chart Fanatics, 21 Sep 2025
(https://youtu.be/tvERE-Beu2U), 3.5 hours.
- The guest claims an audited 218% in the Robbins World Cup (futures).
- The model is explained from minute 2 to minute 48; the rest is live trading.
- The transcript is not stored here. It is the channel's content; use the link.

**Codex** built its own version from the same transcript, without seeing this code:
[codex_audit/fabio_model](../../codex_audit/fabio_model/REPORT.md).

## The model, as he explains it

Both models use auction market theory and the volume profile. **Value area** = the price zone holding about 70% of
a day's trading; **point of control (POC)** = its busiest price; **low-volume node (LVN)** = a thin price level the
market moved through quickly.

**Trend model (New York session, NQ/ES futures):**
- the market must be out of balance, outside the previous day's value area;
- location: the LVN of the impulse leg;
- trigger: aggression, meaning big trades at the LVN (e.g. a filter of 30 contracts a minute on NQ);
- stop just beyond the big trade;
- target: the POC of the previous balance area, taking the whole position off there;
- break-even early.

**Mean-reversion model (London session, summer months):**
- skip the first breakout out of balance;
- take the second swing back inside, at its LVN;
- target the POC.

His numbers: stops of 5–10 NQ ticks (1.25–2.5 points), 0.2–0.5% risk, about 2,400 trades a year, a worst run of 11
losses in a row.

He says step 3, reading the aggression, "you cannot just automate".

## Our test ([lab9.py](lab9.py))

**Data:** 10 years of NASDAQ 100 and S&P 500:
- HistData minute bars for 2016–Jul 2019, checked against Exness: 0-minute timestamp shift, about 2 bp below the
  mid. The buy price is rebuilt from Exness's spread for each minute of the day.
- Exness bid/ask from Aug 2019.

**How the model is built:**
- Profiles use time at price (Market Profile). There is no exchange volume in either source.
- The order-flow trigger is replaced by either a limit order at the LVN or a confirmation candle.
- Stops are 3 × the 1-minute ATR. His 5–10 ticks are smaller than one CFD spread before 2024.

| NASDAQ, avg R per trade | Last 10 yrs | Last 2 yrs | 2026 | EUR 1,000 over 10 yrs at 0.5% risk / 2% risk |
|---|---:|---:|---:|---:|
| Trend, limit at LVN (4,967 trades) | −0.253 | −0.182 | −0.141 | EUR 2 / EUR 0 |
| Trend, confirmation (3,201) | −0.106 | −0.074 | −0.064 | EUR 173 / EUR 0 |
| Mean reversion London, limit (916) | −0.117 | −0.003 | −0.176 | EUR 578 / EUR 96 |
| Mean reversion London, confirmation (552) | −0.059 | +0.043 | +0.093 | EUR 845 / EUR 469 |
| Mean reversion NY, May–Aug (242) | +0.052 | +0.266 | +0.311 | EUR 1,060 / EUR 1,211 |
| Trend, confirmation, **futures-like cost** (0.3 bp) | −0.011 | −0.051 | −0.055 | EUR 776 / EUR 161 |
| Mean reversion London, **futures-like cost** | +0.044 | +0.073 | +0.024 | EUR 1,160 / EUR 1,597 |

- The S&P 500 is negative in every version.
- The summer New York mean reversion on NASDAQ loses on the S&P (−0.22R), so it is noise, not an edge.

### Make it profitable? ([improve.py](improve.py))

There were 48 fixed changes (break-even, stop size, minimum R:R, first two hours, months). The best of each model was
chosen on 2016–2021 only and judged once on 2022–2026:
- **Trend** (break-even, 4 ATR stop, first 2 hours, no summer): 2016–21 −0.135R → **2022–26 −0.072R**. 10 yrs EUR
  1,000 → EUR 411 at 0.5% risk.
- **Mean reversion London** (no break-even, 2 ATR stop, min 1.5R): 2016–21 −0.014R → **2022–26 −0.103R**. 10 yrs
  EUR 1,000 → EUR 839 at 0.5% risk.
- **S&P cross-check:** both lose (−0.11R and −0.21R).

## Verdict

**No mechanical version of this model makes money on CFDs or at futures-like costs, in our build or in Codex's.**
Codex's selected version lost −0.282R a trade in 2022–26.

What is left untested is exactly what he says the edge is:
- big executed orders at the low-volume node, cumulative delta and footprint, from CME exchange data that MT5
  CFD quotes do not contain;
- his discretionary reading of balance and context;
- 5–10 tick stops, which only futures costs allow.

Testing it properly would need CME NQ trade data with the aggressor side, plus a futures account. Exness does not
offer CME futures.

```
python strategies/fabio/fetch_hd_index.py     # HistData NASDAQ 100 / S&P 500 2016-2019 (strategies/fabio/data/)
python strategies/fabio/lab9.py               # the model, ~15 min
python strategies/fabio/improve.py            # the improvement search, ~45 min
```
