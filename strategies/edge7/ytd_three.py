"""2026 so far, trade by trade, for the three add-on strategies on EUR 1,000 (compounded):
 1. gotobi LONG on EURJPY  - buy 15:55 UTC the day before each gotobi day (Monday: Sunday 22:15), stop 55, take
                             profit 30, else sell 00:54 UTC (strategies/explore, round 2);
 2. sterling into the month-end London 4 pm fix - buy GBPUSD (and GBPJPY) 15:45 -> 16:00 London on the last UK
                             business day, stop 25 (strategies/month_end_fix);
 3. NASDAQ noise-area momentum - Zarattini, Aziz & Barbon (strategies/breakouts/lab6.py B2), paper sizing.
Exness bid/ask minute data to 30 Sep plus the October archive file (EURJPY/GBP to 19 Oct, NASDAQ to 16 Oct).

  python strategies/edge7/ytd_three.py
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OCT = Path(r"E:\Projects\New folder\replay_tmp\oct")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "strategies" / "explore"))
sys.path.insert(0, str(ROOT / "strategies" / "breakouts"))
from bot.gotobi_calendar import GotobiCalendar  # noqa: E402  (read only)
from flow_edges import COLS, LON, Px, at, month_end_days  # noqa: E402
import lab  # noqa: E402
import lab6  # noqa: E402

UTC, NY = ZoneInfo("UTC"), ZoneInfo("America/New_York")
START = date(2026, 1, 1)


class Px26(Px):
    """Px from explore data or data/, plus the October 2026 archive file."""
    def __init__(self, sym, pip):
        f = ROOT / "strategies" / "explore" / "data" / f"{sym}_m1.parquet"
        if not f.exists():
            f = ROOT / "data" / f"{sym}_m1.parquet"
        parts = [pd.read_parquet(f, columns=COLS)]
        if sym == "GBPUSDm":
            parts.append(pd.read_parquet(ROOT / "data" / "GBPUSDm_2026_m1.parquet", columns=COLS))
        parts.append(pd.read_parquet(OCT / f"{sym}_2026_10.parquet", columns=COLS))
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated()]
        df = df[df.index >= "2025-11-01"]
        self.sym, self.pip = sym, pip
        self.t = df.index.values.astype("datetime64[m]").astype(np.int64)
        for c in COLS:
            setattr(self, c, df[c].to_numpy())


def compound(rs, risk):
    eq = 1000.0
    path = []
    for r in rs:
        eq *= 1 + risk * r
        path.append(eq)
    return eq, path


def show(title, rows, stop, risks):
    t = pd.DataFrame(rows, columns=["day", "pips"]).dropna()
    t["R"] = t.pips / stop
    t["m"] = pd.to_datetime(t.day).dt.to_period("M")
    print(f"\n=== {title}: {len(t)} trades, {(t.pips > 0).sum()} won ({(t.pips > 0).mean():.0%}), {t.pips.sum():+.1f} pips in total")
    for risk in risks:
        eq, _ = compound(t.R, risk)
        print(f"    EUR 1,000 at {risk:.0%} risk per trade -> EUR {eq:,.0f} ({eq / 1000 - 1:+.1%})")
    g = t.groupby("m").agg(trades=("pips", "size"), won=("pips", lambda x: (x > 0).sum()), pips=("pips", "sum"))
    print("    by month: " + " | ".join(f"{p.strftime('%b')}: {r.trades} tr, {r.pips:+.0f} p" for p, r in g.iterrows()))
    return t


def eurjpy():
    px = Px26("EURJPYm", 0.01)
    got = [d for d in GotobiCalendar().trade_days(START, date(2026, 10, 19))]
    rows = []
    for d in got:
        prev = d - timedelta(days=3 if d.weekday() == 0 else 1)
        e0 = datetime.combine(prev, time(15, 55), UTC) if d.weekday() else datetime.combine(d - timedelta(days=1), time(22, 15), UTC)
        p = lab.tp_trade(px, e0, datetime.combine(d, time(0, 54), UTC), +1, 55, 30)
        rows.append((d, p))
    t = show("1. gotobi LONG on EURJPY (stop 55, take profit 30)", rows, 55, (0.03, 0.06))
    reasons = t.pips.map(lambda x: "take-profit" if x >= 29.9 else "stop" if x <= -54.9 else "time exit")
    print("    exits: " + ", ".join(f"{k} {v}" for k, v in reasons.value_counts().items()))


def gbp():
    import holidays
    me = sorted(d for d in month_end_days(START, date(2026, 10, 31), holidays.UK(years=[2026])) if d <= date(2026, 10, 19))
    for sym, pip in (("GBPUSDm", 1e-4), ("GBPJPYm", 0.01)):
        px = Px26(sym, pip)
        rows = [(d, px.trade(at(d, "15:45", LON), at(d, "16:00", LON), +1, 25)) for d in me]
        t = show(f"2. buy {sym[:-1]} 15:45 -> 16:00 London on the last business day (stop 25)", rows, 25, (0.03, 0.06))
        print("    trades: " + ", ".join(f"{pd.Timestamp(r.day):%d %b} {r.pips:+.1f}" for r in t.itertuples()))


def nasdaq():
    def load26(sym, flow=False):
        cols = lab6.B8 + (["n", "up", "dn"] if flow else [])
        df = pd.concat([pd.read_parquet(ROOT / "data" / f"{sym}_m1.parquet", columns=cols),
                        pd.read_parquet(OCT / f"{sym}_2026_10.parquet", columns=cols)]).sort_index()
        df = df[~df.index.duplicated()]
        return df[df.index >= "2025-09-01"]
    lab6.load = load26
    res, _, pos = lab6.b2_daily("USTECm", positions=True)
    x = res[res.index >= pd.Timestamp(START)]
    p = [q for q in pos if q[0] >= pd.Timestamp(START)]
    eq = 1000 * (1 + x).cumprod()
    traded = (x != 0)
    print(f"\n=== 3. NASDAQ noise-area momentum (paper sizing: 2% daily-volatility target, at most 4x)")
    print(f"    {len(x)} trading days to {x.index.max():%d %b}; a position on {traded.sum()} of them ({traded.mean():.0%}); "
          f"{len(p)} positions in total, {len(p) / max(traded.sum(), 1):.1f} per active day; flat every night")
    print(f"    EUR 1,000 -> EUR {eq.iloc[-1]:,.0f} ({eq.iloc[-1] / 1000 - 1:+.1%}), worst drop {(1 - eq / eq.cummax()).max():.0%}")
    m = (1 + x).groupby(x.index.to_period("M")).prod() - 1
    print("    by month: " + " | ".join(f"{k.strftime('%b')}: {v:+.1%}" for k, v in m.items()))


if __name__ == "__main__":
    eurjpy()
    gbp()
    nasdaq()
