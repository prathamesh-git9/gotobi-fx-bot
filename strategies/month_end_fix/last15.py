"""Follow-up chosen AFTER seeing the grid (so weaker evidence than out_of_sample.py): buy GBPUSD 15:45 -> 16:00
London on the last London business day, the one window that was positive for every stop in both halves.
2006-2026, stops 15/25/40, stop slippage, per year, and EUR 1,000 from 2016 and Jan 2025.

  python strategies/month_end_fix/last15.py
"""
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "src"))
from flow_edges import LON, Px, at, month_end_days, tstat  # noqa: E402
from out_of_sample import OldPx, compound  # noqa: E402

import holidays  # noqa: E402

uk = holidays.UK(years=range(2006, 2027))
me = sorted(month_end_days(date(2006, 1, 1), date(2026, 9, 30), uk))
old = {x: OldPx("GBPUSDm", x) for x in (0.0, 0.5)}
new = Px("GBPUSDm")
for stop in (15, 25, 40):
    rows = []
    for d in me:
        px = old[0.0] if d.year <= 2015 else new
        p = px.trade(at(d, "15:45", LON), at(d, "16:00", LON), +1, stop)
        q = old[0.5].trade(at(d, "15:45", LON), at(d, "16:00", LON), +1, stop) if d.year <= 2015 else p
        if p is not None:
            rows.append((d, p, q))
    df = pd.DataFrame(rows, columns=["d", "p", "q"])
    o, n = df[pd.to_datetime(df.d).dt.year <= 2015], df[pd.to_datetime(df.d).dt.year > 2015]
    slip = df.p.where(df.p != -stop, -stop - 3)
    print(f"\n=== buy GBPUSD 15:45-16:00 London, stop {stop} ===")
    print(f"  2006-15: n {len(o)} {o.p.mean():+.2f} (t {tstat(o.p):.2f}), +0.5 pip spread {o.q.mean():+.2f}"
          f" | 2016-26: n {len(n)} {n.p.mean():+.2f} (t {tstat(n.p):.2f}) | all {df.p.mean():+.2f} (t {tstat(df.p):.2f})"
          f" | stopped {(df.p == -stop).mean():.0%}, +3 pip stop slippage {slip.mean():+.2f}")
    yr = df.groupby(pd.to_datetime(df.d).dt.year).p.sum().round(0).astype(int)
    print("  per year:", " ".join(f"{y}:{v:+d}" for y, v in yr.items()), f"| up {(yr > 0).sum()}/21")
    for start in (date(2016, 1, 1), date(2025, 1, 1)):
        s = df[df.d >= start].p.to_numpy()
        print(f"  EUR 1,000 from {start:%b %Y} ({len(s)} trades): " + " | ".join(
            f"{r:.0%}: EUR {compound(s, r, stop)[0]:,.0f} (drop {compound(s, r, stop)[1]:.0%})" for r in (0.02, 0.06)))
