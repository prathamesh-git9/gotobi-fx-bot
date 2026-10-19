"""The friend's "strategy 2": conditional month-end EURUSD rebalancing into the 4 pm London fix, tested exactly as
written (15:30 -> 15:55 UTC, stop 15 pips, short EURUSD if the S&P 500 in EUR beat the DAX month to date, else
long), plus the London-time version (15:30 -> 15:55 London), because 15:30 UTC is after the fix in summer.
Same data and costs as src/flow_edges.py; EUR 1,000 compounded at 2% and 6% risk from 2016 and from 2025.

  python strategies/month_end_fix/backtest.py
"""
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))   # reads src/flow_edges.py only, never the gotobi bot
from flow_edges import LON, Px, at, month_end_days, tstat, yahoo  # noqa: E402

UTC = ZoneInfo("UTC")
STOP = 15


def compound(p, risk, start):
    """p: pips per trade (stop = 1R). Returns final equity and the worst drop from a peak."""
    eq = peak = 1000.0
    dd = 0.0
    for x in p:
        eq *= 1 + risk * x / STOP
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return eq, dd


def main():
    import holidays
    uk = holidays.UK(years=range(2016, 2027))
    Y = yahoo()
    px = Px("EURUSDm")
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30")]
    me = month_end_days(date(2016, 1, 1), date(2026, 9, 30), uk)

    def signal(d):
        hist = Y.index[Y.index < pd.Timestamp(d)]
        ms = Y.index[Y.index < pd.Timestamp(d.replace(day=1))]
        p, b = hist[-1], ms[-1]
        spx_eur = (Y["^GSPC"][p] / Y["EURUSD=X"][p]) / (Y["^GSPC"][b] / Y["EURUSD=X"][b]) - 1
        dax = Y["^GDAXI"][p] / Y["^GDAXI"][b] - 1
        return -1 if spx_eur > dax else 1

    for label, tz in (("as written, 15:30-15:55 UTC", UTC), ("London time, 15:30-15:55 London", LON)):
        rows = []
        for d in days:
            if d in uk:
                continue
            rows.append((d, px.trade(at(d, "15:30", tz), at(d, "15:55", tz), signal(d), STOP), d in me))
        df = pd.DataFrame(rows, columns=["d", "p", "ev"]).dropna()
        ev, ctrl = df[df.ev], df[~df.ev]
        print(f"\n=== {label} ===")
        print(f"month-ends: n {len(ev)}  {ev.p.mean():+.2f} pips/trade (t {tstat(ev.p):.2f})  win {(ev.p > 0).mean():.0%}"
              f"  | same trade other days: {ctrl.p.mean():+.2f}")
        for a, b in ((2016, 2021), (2022, 2026)):
            s = ev[pd.to_datetime(ev.d).dt.year.between(a, b)].p
            print(f"  {a}-{b}: n {len(s)} {s.mean():+.2f} (t {tstat(s):.2f})")
        yr = ev.groupby(pd.to_datetime(ev.d).dt.year).p.sum().round(1)
        print("  pips per year:", dict(yr))
        for start in (date(2016, 1, 1), date(2025, 1, 1)):
            s = ev[ev.d >= start].p.to_numpy()
            out = []
            for r in (0.02, 0.06):
                eq, dd = compound(s, r, start)
                out.append(f"{r:.0%}: EUR {eq:,.0f} (worst drop {dd:.0%})")
            print(f"  EUR 1,000 from {start:%b %Y} ({len(s)} trades): " + " | ".join(out))


if __name__ == "__main__":
    main()
