"""The 5 variants that passed variants.py, frozen, run on 2006-2015, which the grid never saw. HistData has bid
only, so the ask = bid + the median Exness spread for that minute of the London day in 2016-2018 (the same method
the gotobi 20-year test used), and a stress run adds 0.5 pip. Then EUR 1,000 compounded for each from 2016 and
from Jan 2025 on the real Exness data, at 2% and 6% risk.

  python strategies/month_end_fix/out_of_sample.py
"""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))   # reads src/flow_edges.py only, never the gotobi bot
from flow_edges import COLS, DATA, LON, PIP, Px, at, month_end_days, tstat  # noqa: E402

FROZEN = [("GBPUSDm", "15:30", "16:05", +1, 15), ("GBPUSDm", "14:00", "16:00", +1, 40),
          ("GBPUSDm", "16:00", "16:30", -1, 40), ("EURUSDm", "16:00", "16:30", -1, 25),
          ("EURUSDm", "16:00", "16:30", -1, 40)]


class OldPx(Px):
    def __init__(self, sym, extra):
        bid = pd.read_parquet(HERE / "data" / f"{sym[:6]}_hd_bid_m1.parquet")
        ex = pd.read_parquet(DATA / f"{sym}_2016_m1.parquet", columns=COLS)
        ex = ex[ex.index < "2019-01-01"]
        lon = ex.index.tz_localize("UTC").tz_convert(LON)
        prof = ((ex.aopen - ex.bopen) / PIP[sym]).groupby(lon.hour * 60 + lon.minute).median()
        bl = bid.index.tz_localize("UTC").tz_convert(LON)
        sp = (prof.reindex(bl.hour * 60 + bl.minute).to_numpy() + extra) * PIP[sym]
        self.sym, self.pip = sym, PIP[sym]
        self.t = bid.index.values.astype("datetime64[m]").astype(np.int64)
        self.bopen, self.bhigh, self.blow = bid.bopen.to_numpy(), bid.bhigh.to_numpy(), bid.blow.to_numpy()
        self.aopen, self.ahigh, self.alow = self.bopen + sp, self.bhigh + sp, self.blow + sp


def run(px, days, me, v):
    sym, a, b, side, stop = v
    rows = [(d, px.trade(at(d, a, LON), at(d, b, LON), side, stop), d in me) for d in days]
    return pd.DataFrame(rows, columns=["d", "p", "ev"]).dropna()


def compound(p, risk, stop):
    eq = peak = 1000.0
    dd = 0.0
    for x in p:
        eq *= 1 + risk * x / stop
        peak, dd = max(peak, eq), max(dd, 1 - eq / max(peak, eq))
    return eq, dd


def main():
    import holidays
    uk = holidays.UK(years=range(2006, 2027))
    old_days = [d.date() for d in pd.bdate_range("2006-01-02", "2015-12-31") if d.date() not in uk]
    new_days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30") if d.date() not in uk]
    me = month_end_days(date(2006, 1, 1), date(2026, 9, 30), uk)
    old = {(s, x): OldPx(s, x) for s in ("EURUSDm", "GBPUSDm") for x in (0.0, 0.5)}
    new = {s: Px(s) for s in ("EURUSDm", "GBPUSDm")}
    for v in FROZEN:
        sym, a, b, side, stop = v
        name = f"{'buy' if side > 0 else 'sell'} {sym[:6]} {a}-{b} London, stop {stop}"
        print(f"\n=== {name} ===")
        for x in (0.0, 0.5):
            df = run(old[(sym, x)], old_days, me, v)
            e, c = df[df.ev].p, df[~df.ev].p
            yr = e.groupby(pd.to_datetime(df[df.ev].d).dt.year).sum()
            print(f"  2006-2015 {'(+0.5 pip)' if x else '          '}: n {len(e)} {e.mean():+.2f} pips (t {tstat(e):.2f})"
                  f" ctrl {c.mean():+.2f} | up years {(yr > 0).sum()}/10")
        df = run(new[sym], new_days, me, v)
        e = df[df.ev]
        print(f"  2016-2026 (seen)  : n {len(e)} {e.p.mean():+.2f} pips (t {tstat(e.p):.2f})")
        for start in (date(2016, 1, 1), date(2025, 1, 1)):
            s = e[e.d >= start].p.to_numpy()
            out = [f"{r:.0%}: EUR {compound(s, r, stop)[0]:,.0f} (drop {compound(s, r, stop)[1]:.0%})" for r in (0.02, 0.06)]
            print(f"  EUR 1,000 from {start:%b %Y}: " + " | ".join(out))


if __name__ == "__main__":
    main()
