"""Other forced-flow edges, tested the honest way: rules fixed in advance from the published research, real
Exness bid/ask minutes, a 2016-2021 vs 2022-2026 split, and a control (the same trade at ordinary times).

1. Month-end London 4 pm WM/Reuters fix (Melvin & Prins 2015, J. Int. Money & Finance): foreign holders of US
   equities re-hedge at the month-end fix. If US stocks beat foreign stocks (in USD) month to date, they must
   sell dollars. Trade 14:00 -> 16:00 London on the last London business day: sell USD if the S&P 500 beat the
   average of the DAX, FTSE and Nikkei (in USD) up to the previous close, else buy USD. EURUSD, GBPUSD, USDJPY.
   Control: the same signal and window on every other day.
2. Daily 4 pm fix reversal: the move 15:30 -> 16:00 London is faded 16:00 -> 16:30. EURUSD, GBPUSD, USDJPY.
3. Gold London auctions (LBMA, 10:30 and 15:00 London): XAUUSD 30 minutes into and out of each auction,
   direction = against the move of the previous 30 minutes (auction pressure reverting), and plain drift.
4. US500 month-end close: last trading day, 15:00 -> 16:00 New York, against the month-to-date S&P move
   (pension rebalancing sells winners). 2019 onwards only.

  python src/flow_edges.py
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LON, NY = ZoneInfo("Europe/London"), ZoneInfo("America/New_York")
PIP = {"EURUSDm": 1e-4, "GBPUSDm": 1e-4, "USDJPYm": 1e-2, "XAUUSDm": 0.1, "US500m": 0.1, "DE30m": 0.1}
FILES = {"EURUSDm": ["EURUSDm_2016", "EURUSDm", "EURUSDm_2026_10"], "GBPUSDm": ["GBPUSDm_2016", "GBPUSDm", "GBPUSDm_2026"],
         "USDJPYm": ["USDJPYm_2016", "USDJPYm", "USDJPYm_2026_10"], "XAUUSDm": ["XAUUSDm_2015", "XAUUSDm"],
         "US500m": ["US500m"], "DE30m": ["DE30m"]}
COLS = ["bopen", "bhigh", "blow", "aopen", "ahigh", "alow"]
END = pd.Timestamp("2026-09-30 23:59")


class Px:
    def __init__(self, sym):
        parts = [pd.read_parquet(DATA / f"{f}_m1.parquet", columns=COLS) for f in FILES[sym] if (DATA / f"{f}_m1.parquet").exists()]
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated()]
        df = df[(df.index >= "2016-01-01") & (df.index <= END)]
        self.sym, self.pip, self.start = sym, PIP[sym], df.index[0]
        self.t = df.index.values.astype("datetime64[m]").astype(np.int64)
        for c in COLS:
            setattr(self, c, df[c].to_numpy())

    def idx(self, ts_utc: datetime, tol_min=3):
        k = np.datetime64(ts_utc.replace(tzinfo=None), "m").astype(np.int64)
        i = int(np.searchsorted(self.t, k))
        return i if i < len(self.t) and self.t[i] - k <= tol_min else None

    def trade(self, t0, t1, side, stop_pips):
        """side +1 buy / -1 sell; pips after the spread; stop on the closing side, stop wins ties."""
        i, j = self.idx(t0), self.idx(t1)
        if i is None or j is None or j <= i:
            return None
        sp = (self.aopen[i] - self.bopen[i]) / self.pip
        if side > 0:
            e = self.aopen[i]
            if stop_pips and (self.blow[i:j] <= e - stop_pips * self.pip).any():
                return -stop_pips
            return (self.bopen[j] - e) / self.pip
        e = self.bopen[i]
        if stop_pips and (self.ahigh[i:j] >= e + stop_pips * self.pip).any():
            return -stop_pips
        return (e - self.aopen[j]) / self.pip

    def mid(self, ts_utc):
        i = self.idx(ts_utc)
        return None if i is None else (self.aopen[i] + self.bopen[i]) / 2


def at(d: date, hm: str, tz) -> datetime:
    h, m = map(int, hm.split(":"))
    return datetime.combine(d, time(h, m), tz).astimezone(ZoneInfo("UTC"))


def tstat(x):
    x = np.asarray(x, float)
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x)) if len(x) > 2 else np.nan


def summary(name, rows):
    """rows: list of (date, pips, is_event). Prints event stats by period and the control."""
    df = pd.DataFrame(rows, columns=["d", "p", "ev"]).dropna()
    df["per"] = np.where(pd.to_datetime(df.d).dt.year <= 2021, "2016-21", "2022-26")
    out = []
    for per in ["2016-21", "2022-26"]:
        e = df[(df.per == per) & df.ev].p
        c = df[(df.per == per) & ~df.ev].p
        out.append(f"{per}: n {len(e):4} {e.mean():+6.2f} (t {tstat(e):5.2f})" + (f" ctrl {c.mean():+5.2f}" if len(c) else ""))
    print(f"  {name:44} " + " | ".join(out))
    return df


def yahoo():
    y = pd.read_parquet(DATA / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    return y.pivot(index="date", columns="sym", values="close").sort_index().ffill()


def month_end_days(start: date, end: date, cal) -> set:
    out, d = set(), start
    while d <= end:
        nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
        last = nxt - timedelta(days=1)
        while last.weekday() >= 5 or last in cal:
            last -= timedelta(days=1)
        out.add(last)
        d = nxt
    return out


def main():
    import holidays
    uk = holidays.UK(years=range(2016, 2027))
    us = holidays.NYSE(years=range(2016, 2027))
    Y = yahoo()
    pxs = {s: Px(s) for s in FILES}
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30")]
    me_lon = month_end_days(date(2016, 1, 1), date(2026, 9, 30), uk)

    # month-to-date relative performance, US vs foreign (in USD), up to the previous close
    us_ = Y["^GSPC"]
    foreign = pd.concat([np.log(Y["^GDAXI"] * Y["EURUSD=X"]), np.log(Y["^FTSE"] * Y["GBPUSD=X"]),
                         np.log(Y["^N225"] / Y["USDJPY=X"])], axis=1)

    def rel_mtd(d):
        hist = Y.index[Y.index < pd.Timestamp(d)]
        if not len(hist):
            return np.nan
        prev = hist[-1]
        month_start = Y.index[Y.index < pd.Timestamp(d.replace(day=1))]
        if not len(month_start):
            return np.nan
        base = month_start[-1]
        u = np.log(us_[prev] / us_[base])
        f = (foreign.loc[prev] - foreign.loc[base]).mean()
        return u - f

    rel = {d: rel_mtd(d) for d in days}
    results = {}
    print("Pips per trade after the spread (gold in $0.10, US500 in 0.1 points); 'ctrl' = same trade at ordinary times\n")
    print("1. Month-end London 4 pm fix rebalancing (sell USD if US stocks beat foreign stocks month to date)")
    for s, usd_base, stop in (("EURUSDm", -1, 40), ("GBPUSDm", -1, 50), ("USDJPYm", +1, 50)):
        rows = []
        for d in days:
            if d in uk or np.isnan(rel[d]):
                continue
            usd_dir = -1 if rel[d] > 0 else +1                  # US beat foreign -> sell USD
            side = usd_dir * usd_base                           # EURUSD: selling USD = buying EURUSD
            rows.append((d, pxs[s].trade(at(d, "14:00", LON), at(d, "16:00", LON), side, stop), d in me_lon))
        results[f"ME fix {s}"] = summary(f"{s} 14:00-16:00 London, month-end", rows)
    rows = []
    for d in days:
        if d in uk or d not in me_lon:
            continue
        rows.append((d, pxs["EURUSDm"].trade(at(d, "14:00", LON), at(d, "16:00", LON), +1, 40), True))
    summary("  (EURUSD month-end, always buy: no signal)", rows)

    print("\n2. Daily 4 pm fix reversal (fade 15:30-16:00 London, hold 16:00-16:30)")
    for s, stop in (("EURUSDm", 25), ("GBPUSDm", 30), ("USDJPYm", 30)):
        rows = []
        for d in days:
            if d in uk:
                continue
            a, b = pxs[s].mid(at(d, "15:30", LON)), pxs[s].mid(at(d, "16:00", LON))
            if a is None or b is None or a == b:
                continue
            side = -1 if b > a else +1
            rows.append((d, pxs[s].trade(at(d, "16:00", LON), at(d, "16:30", LON), side, stop), True))
        results[f"fix rev {s}"] = summary(f"{s} fade the run into the 4 pm fix", rows)

    print("\n3. Gold London auctions (XAUUSD; stop $5)")
    g = pxs["XAUUSDm"]
    for hm, pre, post in (("10:30", "10:00", "11:00"), ("15:00", "14:30", "15:30")):
        rows_rev, rows_into, rows_after = [], [], []
        for d in days:
            if d in uk:
                continue
            a, b = g.mid(at(d, pre, LON)), g.mid(at(d, hm, LON))
            if a is None or b is None or a == b:
                continue
            rows_rev.append((d, g.trade(at(d, hm, LON), at(d, post, LON), -1 if b > a else +1, 50), True))
            rows_into.append((d, g.trade(at(d, pre, LON), at(d, hm, LON), -1, 50), True))
            rows_after.append((d, g.trade(at(d, hm, LON), at(d, post, LON), +1, 50), True))
        results[f"gold rev {hm}"] = summary(f"fade the 30 min into the {hm} auction", rows_rev)
        summary(f"short the 30 min into the {hm} auction", rows_into)
        summary(f"long the 30 min after the {hm} auction", rows_after)

    print("\n4. US500 month-end close (against the month-to-date move, 15:00-16:00 New York; 2019-08 onwards)")
    me_ny = month_end_days(date(2019, 8, 1), date(2026, 9, 30), us)
    rows = []
    for d in days:
        if d in us or d < date(2019, 9, 1):
            continue
        hist = Y.index[Y.index < pd.Timestamp(d)]
        ms = Y.index[Y.index < pd.Timestamp(d.replace(day=1))]
        mtd = us_[hist[-1]] / us_[ms[-1]] - 1
        rows.append((d, pxs["US500m"].trade(at(d, "15:00", NY), at(d, "16:00", NY), -1 if mtd > 0 else +1, 300), d in me_ny))
    results["US500 ME"] = summary("US500 last hour, against the MTD move", rows)

    pd.to_pickle(results, ROOT / "results" / "flow_edges.pkl")


if __name__ == "__main__":
    main()
