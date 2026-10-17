"""$1,000 account, last 3 years (Oct 2023 - Sep 2026), rule chosen only on Jan 2019 - Sep 2023.

Rule (gold, XAUUSD, Exness Standard spread):
  previous-day high/low swept during 07:00-16:00 London, 5-min candle closes back inside,
  AND daily trend agrees (prior close above/below both 20- and 50-day SMA),
  AND the reclaim came within 3 candles of the sweep, AND the sweep was <= 0.25x daily ATR deep.
  Stop beyond the sweep wick, target 3R, flat by 20:00 London. 1% risk per trade.
"""
import numpy as np
import pandas as pd

s = pd.read_parquet("../results/signals.parquet")
s["day"] = pd.to_datetime(s["day"])
t = s[(s.sym == "XAUUSDm") & (s.model == "pdhl") & s.trend & s.quick & s.shallow]
t = t[(t.day >= "2023-10-01") & (t.day <= "2026-09-30")].sort_values("time")


def replay(r_col, slip_usd=0.0, start=1000.0, risk_pct=0.01):
    bal, peak, dd, eq, skipped = start, start, 0.0, [], 0
    for risk, r in zip(t.risk.to_numpy(), t[r_col].to_numpy()):
        per_lot = risk * 100                                   # $ per 1.00 lot at the stop (100 oz)
        lots = np.floor(bal * risk_pct / per_lot / 0.01) * 0.01
        if lots < 0.01:
            if 0.01 * per_lot > bal * 0.02:
                skipped += 1
                eq.append(bal)
                continue
            lots = 0.01
        pnl = r * lots * per_lot - slip_usd * lots * 100       # extra slippage on top of spread
        bal += pnl
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
        eq.append(bal)
    return bal, dd, skipped, eq


r = t["r_3.0"]
print(f"trades {len(t)}  ({len(t)/3:.0f}/yr)   win rate {np.mean(r > 0):.0%}   avg {r.mean():+.3f}R   "
      f"longs {np.mean(t.side > 0):.0%}")
streak = best = 0
for x in r:
    streak = streak + 1 if x < 0 else 0
    best = max(best, streak)
print("worst losing streak:", best)
for label, slip in (("spread only", 0.0), ("spread + $0.10/oz slippage", 0.10), ("spread + $0.20/oz slippage", 0.20)):
    bal, dd, sk, eq = replay("r_3.0", slip)
    print(f"  {label:28s} end balance ${bal:,.0f}   max drawdown {dd:.0%}   skipped {sk}")
bal, dd, sk, eq = replay("r_3.0")
yr = t.day.dt.year.to_numpy()
print("balance at each year end:", {int(y): round(eq[np.where(yr == y)[0][-1]]) for y in np.unique(yr)})
print("by year R:", t.groupby(t.day.dt.year)["r_3.0"].agg(["count", "sum"]).round(1).to_dict("index"))

# same trades, shuffled order: how much does luck of sequence matter?
rng = np.random.default_rng(1)
ends, dds = [], []
rr = r.to_numpy()
for _ in range(20000):
    path = 1000 * np.cumprod(1 + 0.01 * rng.choice(rr, len(rr)))
    ends.append(path[-1]); dds.append((1 - path / np.maximum.accumulate(path)).max())
ends = np.array(ends)
print(f"bootstrap of these trades: P(end < $1000) {np.mean(ends < 1000):.0%}   median ${np.median(ends):,.0f}   "
      f"5th-95th pct ${np.percentile(ends, 5):,.0f} - ${np.percentile(ends, 95):,.0f}   "
      f"P(drawdown >= 20%) {np.mean(np.array(dds) >= .2):.0%}")
top5 = r.sort_values(ascending=False)
print(f"total {r.sum():+.1f}R; without best 5 trades {top5.iloc[5:].sum():+.1f}R")
