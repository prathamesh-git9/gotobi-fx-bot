"""Stress test of the one survivor: buy GBPUSD 15:30 -> 16:05 London on the last London business day, stop 15.
Per-year pips over 2006-2026, stops filled 3 and 5 pips worse (the fix can gap through a stop), the same trade on
EURUSD (is it a dollar flow or a sterling quirk?), and how often the stop is hit.

  python strategies/month_end_fix/stress.py
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
from flow_edges import LON, Px, at, month_end_days, tstat  # noqa: E402
from out_of_sample import OldPx  # noqa: E402

import holidays  # noqa: E402

uk = holidays.UK(years=range(2006, 2027))
me = sorted(month_end_days(date(2006, 1, 1), date(2026, 9, 30), uk))
for sym in ("GBPUSDm", "EURUSDm"):
    old, new = OldPx(sym, 0.0), Px(sym)
    rows = []
    for d in me:
        px = old if d.year <= 2015 else new
        p = px.trade(at(d, "15:30", LON), at(d, "16:05", LON), +1, 15)
        if p is not None:
            rows.append((d, p))
    df = pd.DataFrame(rows, columns=["d", "p"])
    print(f"\n=== buy {sym[:6]} 15:30-16:05 London, month-end, stop 15: n {len(df)} {df.p.mean():+.2f} pips"
          f" (t {tstat(df.p):.2f}), win {(df.p > 0).mean():.0%}, stopped {(df.p == -15).mean():.0%}")
    for slip in (3, 5):
        q = df.p.where(df.p != -15, -15 - slip)
        print(f"  stops filled {slip} pips worse: {q.mean():+.2f} (t {tstat(q):.2f})")
    yr = df.groupby(pd.to_datetime(df.d).dt.year).p.sum().round(0).astype(int)
    print("  pips per year:", " ".join(f"{y}:{v:+d}" for y, v in yr.items()))
    print(f"  up years {(yr > 0).sum()}/{len(yr)}")
