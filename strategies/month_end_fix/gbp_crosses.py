"""Is the month-end sterling buying at the London 4 pm fix also in GBPJPY? Round 3 (strategies/explore/lab3.py, M)
found GBPJPY rising 15:45 -> 16:00 London on the last UK business day (+3.5 pips, 2016-2026) - but that was found
by looking. Here the same frozen rule (buy 15:45, sell 16:00 London, stop 25) is run on 2006-2015, which it never
saw (HistData bid + the median Exness GBPJPY spread for that London minute in 2016-2018), next to the ordinary
days as the control, and per year.

  python strategies/month_end_fix/gbp_crosses.py              # GBPJPY 2006-2015 / 2016-2026
  python strategies/month_end_fix/gbp_crosses.py --combined   # GBPUSD vs GBPJPY on the same month-ends
"""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
from flow_edges import COLS, LON, Px, at, month_end_days, tstat  # noqa: E402

import holidays  # noqa: E402


class OldGBPJPY(Px):
    def __init__(self, extra=0.0):
        bid = pd.read_parquet(HERE / "data" / "GBPJPY_hd_bid_m1.parquet")
        ex = pd.read_parquet(ROOT / "strategies" / "explore" / "data" / "GBPJPYm_m1.parquet", columns=COLS)
        ex = ex[ex.index < "2019-01-01"]
        lon = ex.index.tz_localize("UTC").tz_convert(LON)
        prof = ((ex.aopen - ex.bopen) / 0.01).groupby(lon.hour * 60 + lon.minute).median()
        bl = bid.index.tz_localize("UTC").tz_convert(LON)
        sp = (prof.reindex(bl.hour * 60 + bl.minute).fillna(prof.median()).to_numpy() + extra) * 0.01
        self.sym, self.pip = "GBPJPYm", 0.01
        self.t = bid.index.values.astype("datetime64[m]").astype(np.int64)
        self.bopen, self.bhigh, self.blow = bid.bopen.to_numpy(), bid.bhigh.to_numpy(), bid.blow.to_numpy()
        self.aopen, self.ahigh, self.alow = self.bopen + sp, self.bhigh + sp, self.blow + sp


class NewGBPJPY(Px):
    def __init__(self):
        df = pd.read_parquet(ROOT / "strategies" / "explore" / "data" / "GBPJPYm_m1.parquet", columns=COLS)
        df = df[df.index <= "2026-09-30 23:59"]
        self.sym, self.pip = "GBPJPYm", 0.01
        self.t = df.index.values.astype("datetime64[m]").astype(np.int64)
        for c in COLS:
            setattr(self, c, df[c].to_numpy())


def main():
    uk = holidays.UK(years=range(2006, 2027))
    me = month_end_days(date(2006, 1, 1), date(2026, 9, 30), uk)
    for label, px, a, b in (("2006-2015 (never seen)", OldGBPJPY(), "2006-01-02", "2015-12-31"),
                            ("2006-2015, +0.5 pip extra spread", OldGBPJPY(0.5), "2006-01-02", "2015-12-31"),
                            ("2016-2026 (where it was found)", NewGBPJPY(), "2016-01-04", "2026-09-30")):
        days = [d.date() for d in pd.bdate_range(a, b) if d.date() not in uk]
        rows = [(d, px.trade(at(d, "15:45", LON), at(d, "16:00", LON), +1, 25), d in me) for d in days]
        df = pd.DataFrame(rows, columns=["d", "p", "ev"]).dropna()
        e, c = df[df.ev], df[~df.ev]
        yr = e.groupby(pd.to_datetime(e.d).dt.year).p.sum()
        print(f"\nbuy GBPJPY 15:45-16:00 London on the last UK business day, stop 25 pips: {label}")
        print(f"   month-ends: n {len(e)} {e.p.mean():+.2f} pips (t {tstat(e.p):.2f}), win {(e.p > 0).mean():.0%} | ordinary days "
              f"{c.p.mean():+.2f} | years up {(yr > 0).sum()}/{len(yr)}")
        print("   per year:", " ".join(f"{y}:{v:+.0f}" for y, v in yr.items()))



def combined():
    """GBPUSD and GBPJPY on the same month-ends: correlation, and a half-each split vs GBPUSD alone (R = pips/25)."""
    sys.path.insert(0, str(HERE))
    from out_of_sample import OldPx  # noqa: E402
    uk = holidays.UK(years=range(2006, 2027))
    me = sorted(month_end_days(date(2006, 1, 1), date(2026, 9, 30), uk))
    gu_old, gu_new = OldPx("GBPUSDm", 0.0), Px("GBPUSDm")
    gj_old, gj_new = OldGBPJPY(), NewGBPJPY()
    rows = []
    for d in me:
        gu, gj = (gu_old, gj_old) if d.year <= 2015 else (gu_new, gj_new)
        a = gu.trade(at(d, "15:45", LON), at(d, "16:00", LON), +1, 25)
        b = gj.trade(at(d, "15:45", LON), at(d, "16:00", LON), +1, 25)
        if a is not None and b is not None:
            rows.append((d, a / 25, b / 25))
    df = pd.DataFrame(rows, columns=["d", "gu", "gj"])
    df["half"] = (df.gu + df.gj) / 2
    print(f"\nGBPUSD vs GBPJPY on the same {len(df)} month-ends 2006-2026: correlation {df.gu.corr(df.gj):.2f}")
    for col, name in (("gu", "GBPUSD alone"), ("gj", "GBPJPY alone"), ("half", "half each")):
        x = df[col]
        worst = x.rolling(12).sum().min()
        print(f"   {name:13}: {x.mean():+.3f}R a month-end (t {tstat(x):.2f}), worst 12-month run {worst:+.2f}R, "
              f"2006-15 {x[pd.to_datetime(df.d).dt.year <= 2015].mean():+.3f}R | 2016-26 {x[pd.to_datetime(df.d).dt.year > 2015].mean():+.3f}R")


if __name__ == "__main__":
    combined() if "--combined" in sys.argv else main()
