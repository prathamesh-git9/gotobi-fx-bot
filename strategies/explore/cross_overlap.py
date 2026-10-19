"""Is gotobi on EURJPY a second edge or the same bet twice? Correlation of per-trade results with USDJPY on the
same days, and what splitting the risk across both pairs does (in R, stop 55 = 1R).

  python strategies/explore/cross_overlap.py
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lab import UTC, GotobiCalendar, XPx, tp_trade  # noqa: E402

got = GotobiCalendar().trade_days(date(2016, 1, 1), date(2026, 9, 30))
res = {}
for sym in ("USDJPYm", "EURJPYm"):
    px = XPx(sym)
    rows = {}
    for d in got:
        prev = d - timedelta(days=3 if d.weekday() == 0 else 1)
        e0 = datetime.combine(prev, time(15, 55), UTC) if d.weekday() else datetime.combine(d - timedelta(days=1), time(22, 15), UTC)
        rows[d] = tp_trade(px, e0, datetime.combine(d, time(0, 54), UTC), +1, 55, 30)
    res[sym] = pd.Series(rows, dtype=float)
df = pd.DataFrame(res).dropna() / 55
print(f"days {len(df)}, correlation of per-trade R: {df.corr().iloc[0, 1]:.2f}")
for name, r in (("USDJPY only", df.USDJPYm), ("EURJPY only", df.EURJPYm), ("half each", df.mean(axis=1))):
    print(f"  {name:12} mean {r.mean():+.4f}R  sd {r.std():.3f}  mean/sd {r.mean() / r.std():.3f}  "
          f"worst 20-trade run {r.rolling(20).sum().min():+.2f}R")


def grow(r, risk):
    eq = peak = 1000.0
    dd = 0.0
    for x in r:
        eq *= 1 + risk * x
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return eq, dd


print("\nEUR 1,000, longs only (stop 55 pips = 1R; the bot's shorts are not included here)")
for start in (date(2016, 1, 1), date(2025, 1, 1)):
    sub = df[df.index >= start]
    for name, r in (("USDJPY only", sub.USDJPYm), ("EURJPY only", sub.EURJPYm), ("half each", sub.mean(axis=1))):
        out = " | ".join(f"{k:.0%}: EUR {grow(r, k)[0]:,.0f} (drop {grow(r, k)[1]:.0%})" for k in (0.02, 0.06))
        print(f"  from {start:%b %Y} {name:12} {out}")
