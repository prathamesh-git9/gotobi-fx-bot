"""Modifications of strategy 2, a fixed grid decided before looking at any result. A variant only counts if it
makes money in BOTH 2016-21 and 2022-26, beats the same trade on ordinary days, and has t > 2 over the whole
period (and with ~200 variants, one in twenty will pass t > 2 by luck alone, so even that is a weak bar).

  python strategies/month_end_fix/variants.py
"""
import itertools
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
# entry, exit (London time unless noted)
WINDOWS = {"14:00-16:00": ("14:00", "16:00"), "15:00-15:55": ("15:00", "15:55"), "15:30-15:55": ("15:30", "15:55"),
           "15:30-16:05": ("15:30", "16:05"), "15:45-16:00": ("15:45", "16:00"), "16:00-16:30": ("16:00", "16:30"),
           "16:00-17:00": ("16:00", "17:00")}
SIGNALS = ["spx_vs_dax", "inverse", "always_buy", "always_sell", "big_gap_2pct", "big_gap_inverse"]
DAYS_SET = ["month_end", "quarter_end", "month_end_minus1"]
STOPS = [15, 25, 40]


def main():
    import holidays
    uk = holidays.UK(years=range(2016, 2027))
    Y = yahoo()
    px = {s: Px(s) for s in ("EURUSDm", "GBPUSDm")}
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30") if d.date() not in uk]
    me = month_end_days(date(2016, 1, 1), date(2026, 9, 30), uk)
    pos = {d: i for i, d in enumerate(days)}
    me1 = {days[pos[d] - 1] for d in me if d in pos and pos[d] > 0}
    qe = {d for d in me if d.month in (3, 6, 9, 12)}
    events = {"month_end": me, "quarter_end": qe, "month_end_minus1": me1}

    gap = {}
    for d in days:
        hist = Y.index[Y.index < pd.Timestamp(d)]
        ms = Y.index[Y.index < pd.Timestamp(d.replace(day=1))]
        p, b = hist[-1], ms[-1]
        spx_eur = (Y["^GSPC"][p] / Y["EURUSD=X"][p]) / (Y["^GSPC"][b] / Y["EURUSD=X"][b]) - 1
        gap[d] = spx_eur - (Y["^GDAXI"][p] / Y["^GDAXI"][b] - 1)

    def side(sig, d):
        g = gap[d]
        return {"spx_vs_dax": -1 if g > 0 else 1, "inverse": 1 if g > 0 else -1, "always_buy": 1, "always_sell": -1,
                "big_gap_2pct": (-1 if g > 0 else 1) if abs(g) > 0.02 else 0,
                "big_gap_inverse": (1 if g > 0 else -1) if abs(g) > 0.02 else 0}[sig]

    out = []
    for sym, (wn, (a, b)), sig, stop in itertools.product(px, WINDOWS.items(), SIGNALS, STOPS):
        allrows = []
        for d in days:
            s = side(sig, d)
            if s:
                allrows.append((d, px[sym].trade(at(d, a, LON), at(d, b, LON), s, stop)))
        df = pd.DataFrame(allrows, columns=["d", "p"]).dropna()
        yr = pd.to_datetime(df.d).dt.year
        for dn, evset in events.items():
            ev = df.d.isin(evset)
            e, c = df[ev].p, df[~ev].p
            h1, h2 = df[ev & (yr <= 2021)].p, df[ev & (yr >= 2022)].p
            out.append(dict(sym=sym, window=wn, signal=sig, days=dn, stop=stop, n=len(e), pips=e.mean(), t=tstat(e),
                            ctrl=c.mean(), h1=h1.mean(), h2=h2.mean(), t1=tstat(h1), t2=tstat(h2)))
    r = pd.DataFrame(out)
    r["passes"] = (r.h1 > 0) & (r.h2 > 0) & (r.pips > r.ctrl) & (r.t > 2)
    r.to_csv(ROOT / "results" / "month_end_fix_variants.csv", index=False)
    pd.set_option("display.width", 200)
    print(f"{len(r)} variants tested, {r.passes.sum()} pass all four tests, "
          f"{((r.h1 > 0) & (r.h2 > 0)).sum()} make money in both halves")
    cols = ["sym", "window", "signal", "days", "stop", "n", "pips", "t", "ctrl", "h1", "h2"]
    print("\nPassing:" if r.passes.any() else "\nNothing passes. Best 12 by t (both halves positive):")
    show = r[r.passes] if r.passes.any() else r[(r.h1 > 0) & (r.h2 > 0)]
    print(show.sort_values("t", ascending=False)[cols].head(12).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
