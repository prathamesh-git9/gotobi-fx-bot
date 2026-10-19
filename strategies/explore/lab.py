"""Round 2 of the hunt for scheduled-flow edges (my half; Codex tests a different list in codex_audit/explore2).
Every rule is written below BEFORE running it. Each is judged on 2016-21 and 2022-26 separately (BTC: 2019-21 vs
2022-26) against the same trade at ordinary times, after the real Exness bid/ask spread.

 A. Gotobi in other yen pairs: EURJPY, AUDJPY, the bot's two trades on gotobi days vs ordinary Tokyo days.
 B. USD-into-the-month-end-fix in other pairs: buy AUDUSD / sell USDCHF... (does the GBPUSD effect generalise?)
    15:45 -> 16:00 London, last London business day, stop 25.
 C. China: USDCNH into month-end (exporters sell dollars): short USDCNH 01:00 UTC -> 08:00 UTC on the last 3
    Chinese business days; and the 09:15 Beijing PBoC fix: follow the 01:15-01:20 UTC move until 02:00.
 D. Shanghai Gold Benchmark auctions (10:15 and 14:15 Beijing = 02:15 / 06:15 UTC): long the 30 min into each,
    and fade the 30 min before, holding 30 min after.
 E. Silver: London silver price (12:00 London): long the 30 min into it, fade after.
 F. Bitcoin: (1) CME weekend gap: fade Sunday 23:00 UTC -> Monday 15:00 UTC toward the Friday 21:00 UTC price when
    the gap > 1%; (2) perpetual funding times 00/08/16 UTC: short the 30 min into each, long the 30 min after;
    (3) spot-ETF NAV fix (16:00 New York, since 11 Jan 2024): 15:00 -> 16:00 NY long, 16:00 -> 17:00 NY short;
    (4) monthly options/futures expiry (last Friday 08:00 UTC): short 06:00 -> 08:00, long 08:00 -> 10:00.
 G. Index expiry auctions on the third Friday of each month (2019-08+): DAX (13:00 Frankfurt intraday auction),
    FTSE (10:15 London EDSP auction), US500 (options settle at the 09:30 NY open). Long and short the 30 min into
    and out of each, vs the same window on other Fridays.

  python strategies/explore/lab.py [A B C ...]
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from bot.gotobi_calendar import GotobiCalendar  # noqa: E402  (read only)
from flow_edges import COLS, FILES, LON, NY, Px, at, month_end_days, tstat  # noqa: E402

UTC = ZoneInfo("UTC")
PIP = {"EURJPYm": 0.01, "AUDJPYm": 0.01, "AUDUSDm": 1e-4, "USDCNHm": 1e-4, "XAUUSDm": 0.1, "XAGUSDm": 0.01,
       "BTCUSDm": 1.0, "DE30m": 0.1, "UK100m": 0.1, "US500m": 0.1, "USDJPYm": 0.01, "GBPUSDm": 1e-4, "EURUSDm": 1e-4}
RESULTS = []


class XPx(Px):
    """Px for a file in strategies/explore/data (or data/ for the old symbols)."""
    def __init__(self, sym):
        f = HERE / "data" / f"{sym}_m1.parquet"
        if not f.exists() and sym in FILES:
            return Px.__init__(self, sym)
        if not f.exists():
            f = ROOT / "data" / f"{sym}_m1.parquet"
        df = pd.read_parquet(f, columns=COLS)
        df = df[(df.index >= "2016-01-01") & (df.index <= "2026-09-30 23:59")]
        self.sym, self.pip = sym, PIP[sym]
        self.t = df.index.values.astype("datetime64[m]").astype(np.int64)
        for c in COLS:
            setattr(self, c, df[c].to_numpy())


def judge(name, rows, split=2021):
    """rows: (date, pips, is_event). Event mean per half, control, verdict."""
    df = pd.DataFrame(rows, columns=["d", "p", "ev"]).dropna()
    if df.empty:
        print(f"  {name}: no trades")
        return
    y = pd.to_datetime(df.d).dt.year
    e, c = df[df.ev], df[~df.ev]
    h1, h2 = df[df.ev & (y <= split)].p, df[df.ev & (y > split)].p
    ok = len(h1) > 5 and len(h2) > 5 and h1.mean() > 0 and h2.mean() > 0 and (c.empty or e.p.mean() > c.p.mean()) \
        and tstat(e.p) > 2
    yr = e.groupby(pd.to_datetime(e.d).dt.year).p.sum()
    RESULTS.append(dict(name=name, n=len(e), pips=e.p.mean(), t=tstat(e.p), h1=h1.mean(), h2=h2.mean(),
                        ctrl=c.p.mean() if len(c) else np.nan, up_years=f"{(yr > 0).sum()}/{len(yr)}", passes=ok))
    print(f"  {'PASS' if ok else 'fail'} {name:58} n {len(e):5} {e.p.mean():+7.2f} (t {tstat(e.p):5.2f}) | "
          f"halves {h1.mean():+6.2f} / {h2.mean():+6.2f} | ctrl {c.p.mean() if len(c) else float('nan'):+6.2f} | "
          f"up yrs {(yr > 0).sum()}/{len(yr)}")


def tokyo_days():
    import holidays
    jp = holidays.Japan(years=range(2016, 2027))
    return [d.date() for d in pd.bdate_range("2016-01-05", "2026-09-30") if d.date() not in jp
            and not (d.month == 12 and d.day == 31) and not (d.month == 1 and d.day <= 3)]


def A():
    print("\nA. Gotobi in other yen pairs (long 15:55 UTC day before -> 00:54 UTC, stop 55, TP 30; short 00:55 -> 01:25)")
    got = set(GotobiCalendar().trade_days(date(2016, 1, 1), date(2026, 9, 30)))
    days = tokyo_days()
    for sym in ("EURJPYm", "AUDJPYm", "USDJPYm"):
        try:
            px = XPx(sym)
        except FileNotFoundError:
            print(f"  {sym}: not downloaded yet")
            continue
        longs, shorts = [], []
        for d in days:
            prev = d - timedelta(days=3 if d.weekday() == 0 else 1)
            e0 = datetime.combine(prev, time(15, 55), UTC)
            if d.weekday() == 0:
                e0 = datetime.combine(d - timedelta(days=1), time(22, 15), UTC)      # after the Sunday reopen
            longs.append((d, tp_trade(px, e0, datetime.combine(d, time(0, 54), UTC), +1, 55, 30), d in got))
            shorts.append((d, px.trade(datetime.combine(d, time(0, 55), UTC), datetime.combine(d, time(1, 25), UTC), -1, 55), d in got))
        judge(f"{sym} gotobi long", longs)
        judge(f"{sym} gotobi short", shorts)


def tp_trade(px, t0, t1, side, stop, tp):
    i, j = px.idx(t0, tol_min=20), px.idx(t1)
    if i is None or j is None or j <= i:
        return None
    if side > 0:
        e = px.aopen[i]
        s = np.nonzero(px.blow[i:j] <= e - stop * px.pip)[0]
        g = np.nonzero(px.bhigh[i:j] >= e + tp * px.pip)[0]
    else:
        e = px.bopen[i]
        s = np.nonzero(px.ahigh[i:j] >= e + stop * px.pip)[0]
        g = np.nonzero(px.alow[i:j] <= e - tp * px.pip)[0]
    s = s[0] if len(s) else 10**9
    g = g[0] if len(g) else 10**9
    if s <= g and s < 10**9:
        return -stop
    if g < 10**9:
        return tp
    return ((px.bopen[j] - e) if side > 0 else (e - px.aopen[j])) / px.pip


def B():
    print("\nB. Dollar into the month-end London 4 pm fix, other pairs (15:45 -> 16:00 London, stop 25)")
    import holidays
    uk = holidays.UK(years=range(2016, 2027))
    me = month_end_days(date(2016, 1, 1), date(2026, 9, 30), uk)
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30") if d.date() not in uk]
    for sym, side in (("AUDUSDm", +1), ("GBPUSDm", +1), ("EURUSDm", +1), ("USDJPYm", -1), ("EURJPYm", +1), ("XAUUSDm", +1)):
        px = XPx(sym)
        stop = 25 if sym != "XAUUSDm" else 50
        judge(f"{'buy' if side > 0 else 'sell'} {sym} into the month-end fix",
              [(d, px.trade(at(d, "15:45", LON), at(d, "16:00", LON), side, stop), d in me) for d in days])


def C():
    print("\nC. China: USDCNH into month-end, and the 09:15 Beijing fix")
    import holidays
    cn = holidays.China(years=range(2016, 2027))
    px = XPx("USDCNHm")
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30") if d.date() not in cn]
    last3 = set()
    by_m = {}
    for d in days:
        by_m.setdefault((d.year, d.month), []).append(d)
    for v in by_m.values():
        last3.update(v[-3:])
    judge("short USDCNH 01:00-08:00 UTC, last 3 CN business days",
          [(d, px.trade(datetime.combine(d, time(1), UTC), datetime.combine(d, time(8), UTC), -1, 150), d in last3) for d in days])
    rows = []
    for d in days:
        a, b = px.mid(datetime.combine(d, time(1, 15), UTC)), px.mid(datetime.combine(d, time(1, 20), UTC))
        if a is None or b is None or a == b:
            continue
        rows.append((d, px.trade(datetime.combine(d, time(1, 20), UTC), datetime.combine(d, time(2), UTC), 1 if b > a else -1, 100), True))
    judge("USDCNH follow the first 5 min after the fix, to 02:00 UTC", rows)


def D():
    print("\nD. Shanghai Gold Benchmark auctions (02:15 and 06:15 UTC)")
    px = XPx("XAUUSDm")
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30")]
    for hm, h in (("10:15 Beijing", 2), ("14:15 Beijing", 6)):
        fix = lambda d: datetime.combine(d, time(h, 15), UTC)  # noqa: E731
        judge(f"long gold 30 min into the {hm} auction",
              [(d, px.trade(fix(d) - timedelta(minutes=30), fix(d), +1, 50), True) for d in days])
        rows = []
        for d in days:
            a, b = px.mid(fix(d) - timedelta(minutes=30)), px.mid(fix(d))
            if a is None or b is None or a == b:
                continue
            rows.append((d, px.trade(fix(d), fix(d) + timedelta(minutes=30), -1 if b > a else 1, 50), True))
        judge(f"fade the 30 min into the {hm} auction", rows)


def E():
    print("\nE. London silver price (12:00 London)")
    px = XPx("XAGUSDm")
    import holidays
    uk = holidays.UK(years=range(2016, 2027))
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30") if d.date() not in uk]
    judge("long silver 11:30-12:00 London", [(d, px.trade(at(d, "11:30", LON), at(d, "12:00", LON), +1, 30), True) for d in days])
    rows = []
    for d in days:
        a, b = px.mid(at(d, "11:30", LON)), px.mid(at(d, "12:00", LON))
        if a is None or b is None or a == b:
            continue
        rows.append((d, px.trade(at(d, "12:00", LON), at(d, "12:30", LON), -1 if b > a else 1, 30), True))
    judge("fade the 30 min into the silver price", rows)


def F():
    print("\nF. Bitcoin (pips = USD per 1 BTC)")
    px = XPx("BTCUSDm")
    days = [d.date() for d in pd.bdate_range("2019-01-07", "2026-09-30")]
    rows = []
    for d in days:
        if d.weekday() != 0:
            continue
        fri = datetime.combine(d - timedelta(days=3), time(21), UTC)
        sun = datetime.combine(d - timedelta(days=1), time(23), UTC)
        a, b = px.mid(fri), px.mid(sun)
        if a is None or b is None or abs(b / a - 1) <= 0.01:
            continue
        stop = abs(b - a) * 2
        rows.append((d, px.trade(sun, datetime.combine(d, time(15), UTC), -1 if b > a else 1, stop), True))
    judge("fade the CME weekend gap > 1%, Sun 23:00 -> Mon 15:00 UTC", rows)
    all_days = [d.date() for d in pd.date_range("2019-01-01", "2026-09-30")]
    for h in (0, 8, 16):
        f = lambda d: datetime.combine(d, time(h), UTC)  # noqa: E731
        stop = lambda d: (px.mid(f(d)) or 1e9) * 0.02  # noqa: E731
        judge(f"short BTC 30 min into the {h:02d}:00 UTC funding", [(d, px.trade(f(d) - timedelta(minutes=30), f(d), -1, stop(d)), True) for d in all_days])
        judge(f"long BTC 30 min after the {h:02d}:00 UTC funding", [(d, px.trade(f(d), f(d) + timedelta(minutes=30), +1, stop(d)), True) for d in all_days])
    import holidays
    us = holidays.NYSE(years=range(2019, 2027))
    tdays = [d for d in days if d not in us]
    stop = lambda d: (px.mid(at(d, "15:00", NY)) or 1e9) * 0.03  # noqa: E731
    judge("long BTC 15:00-16:00 NY (ETF NAV), event = since ETFs",
          [(d, px.trade(at(d, "15:00", NY), at(d, "16:00", NY), +1, stop(d)), d >= date(2024, 1, 11)) for d in tdays], split=2024)
    judge("short BTC 16:00-17:00 NY (after ETF NAV), event = since ETFs",
          [(d, px.trade(at(d, "16:00", NY), at(d, "17:00", NY), -1, stop(d)), d >= date(2024, 1, 11)) for d in tdays], split=2024)
    fridays = [d for d in days if d.weekday() == 4]
    last_fri = {max(g) for _, g in pd.Series(fridays).groupby([pd.Series(fridays).map(lambda x: (x.year, x.month))])}
    for lab, a_, b_, side in (("short 06:00-08:00", 6, 8, -1), ("long 08:00-10:00", 8, 10, +1)):
        judge(f"BTC monthly expiry Friday {lab} UTC",
              [(d, px.trade(datetime.combine(d, time(a_), UTC), datetime.combine(d, time(b_), UTC), side,
                            (px.mid(datetime.combine(d, time(a_), UTC)) or 1e9) * 0.03), d in last_fri) for d in fridays])


def G():
    print("\nG. Index expiry auctions, third Fridays vs other Fridays (pips = 0.1 index point)")
    fridays = [d.date() for d in pd.bdate_range("2019-09-01", "2026-09-30") if d.weekday() == 4]
    third = {d for d in fridays if 15 <= d.day <= 21}
    CET = ZoneInfo("Europe/Berlin")
    for sym, hm, tz, stop in (("DE30m", "13:00", CET, 400), ("UK100m", "10:15", LON, 300), ("US500m", "09:30", NY, 200)):
        px = XPx(sym)
        h, m = map(int, hm.split(":"))
        for lab, d0, d1 in (("into", -30, 0), ("after", 0, 30)):
            for side in (+1, -1):
                rows = []
                for d in fridays:
                    fx = at(d, hm, tz)
                    rows.append((d, px.trade(fx + timedelta(minutes=d0), fx + timedelta(minutes=d1), side, stop), d in third))
                judge(f"{'long' if side > 0 else 'short'} {sym} 30 min {lab} the {hm} expiry", rows)


if __name__ == "__main__":
    for k in sys.argv[1:] or "ABCDEFG":
        globals()[k]()
    pd.DataFrame(RESULTS).to_csv(HERE / "lab_results.csv", index=False)
