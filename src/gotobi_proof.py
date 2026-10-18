"""Does the Gotobi strategy really work? A plain, independent check that does not use the bot or any tuned result.

The bot's two trades are priced minute by minute on bid/ask data, on gotobi days AND on every ordinary Tokyo
business day, so a market-wide drift cannot pass for a gotobi effect:
  long:  buy (ask) 15:55 UTC the day before, 55-pip stop, +30-pip take-profit, else sell (bid) 00:54 UTC
  short: sell (bid) 00:55 UTC, 55-pip stop, buy back (ask) 01:25 UTC
A bar that touches both the stop and the target counts as the stop. Entries scheduled in the weekend closure go
in 15 minutes after the reopen; any entry with a spread above 5 pips is skipped (the bot's rules).

Data: 2006-2015 HistData bid + the 2016-18 Exness spread profile (src/gotobi_20y.py; never used to design the
strategy), 2016-2026 real Exness bid/ask (USDJPYm).

  python src/gotobi_proof.py
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bot.gotobi_calendar import GotobiCalendar  # noqa: E402
from bot.replay import load_bars  # noqa: E402

PIP = 0.01
STOP, TP, MAX_SPREAD = 55.0, 30.0, 5.0
COLS = ["bopen", "bhigh", "blow", "aopen", "ahigh", "alow"]


def load() -> pd.DataFrame:
    old = pd.read_parquet(ROOT / "data/histdata/USDJPY_hd_model_2006_2015_m1.parquet", columns=COLS)
    new = load_bars()[COLS]
    new.index = new.index.tz_localize(None) if new.index.tz is not None else new.index
    new = new.loc["2016-01-01":]
    return pd.concat([old.loc[:"2015-12-31 23:59"], new]).sort_index()


class Prices:
    def __init__(self, df: pd.DataFrame):
        self.t = df.index.values.astype("datetime64[m]").astype(np.int64)
        for c in COLS:
            setattr(self, c, df[c].to_numpy())

    def at_or_after(self, ts: datetime) -> int:
        return int(np.searchsorted(self.t, np.datetime64(ts, "m").astype(np.int64)))

    def minute(self, i: int) -> datetime:
        return datetime(1970, 1, 1) + timedelta(minutes=int(self.t[i]))


def long_trade(p: Prices, d: date):
    entry_s = datetime.combine(d - timedelta(days=1), time(15, 55))
    exit_s = datetime.combine(d, time(0, 54))
    i = p.at_or_after(entry_s)
    if i >= len(p.t):
        return None
    if p.minute(i) - entry_s > timedelta(minutes=60):          # weekend closure: 15 min after the reopen
        i = p.at_or_after(p.minute(i) + timedelta(minutes=15))
    j = p.at_or_after(exit_s)
    if j >= len(p.t) or i >= j or p.minute(i) > exit_s - timedelta(minutes=30) or p.minute(j) - exit_s > timedelta(minutes=5):
        return None
    if (p.aopen[i] - p.bopen[i]) / PIP > MAX_SPREAD:
        return None
    e = p.aopen[i]
    stop_hit = np.nonzero(p.blow[i:j] <= e - STOP * PIP)[0]
    tp_hit = np.nonzero(p.bhigh[i:j] >= e + TP * PIP)[0]
    s = stop_hit[0] if len(stop_hit) else 10**9
    t = tp_hit[0] if len(tp_hit) else 10**9
    if s <= t and s < 10**9:
        return -STOP
    if t < 10**9:
        return TP
    return (p.bopen[j] - e) / PIP


def short_trade(p: Prices, d: date):
    fix = datetime.combine(d, time(0, 55))
    i, j = p.at_or_after(fix), p.at_or_after(fix + timedelta(minutes=30))
    if j >= len(p.t) or p.minute(i) != fix or p.minute(j) - (fix + timedelta(minutes=30)) > timedelta(minutes=5):
        return None
    if (p.aopen[i] - p.bopen[i]) / PIP > MAX_SPREAD:
        return None
    e = p.bopen[i]
    if (p.ahigh[i:j] >= e + STOP * PIP).any():
        return -STOP
    return (e - p.aopen[j]) / PIP


def tstat(x) -> float:
    x = np.asarray(x, float)
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x)) if len(x) > 2 else float("nan")


def main() -> None:
    p = Prices(load())
    cal = GotobiCalendar()
    first, last = date(2006, 1, 4), date(2026, 10, 16)
    gotobi = set(cal.trade_days(first, last))
    rows = []
    d = first
    while d <= last:
        if cal.business_day(d) and f"{d:%m-%d}" not in cal.fx_closed:
            rows.append((d, d in gotobi, long_trade(p, d), short_trade(p, d)))
        d += timedelta(days=1)
    df = pd.DataFrame(rows, columns=["day", "gotobi", "long", "short"])
    df["year"] = [x.year for x in df.day]
    df["period"] = np.where(df.year <= 2015, "2006-2015 (unseen)", "2016-2026")

    print("Pips per trade (after the spread). 'ordinary' = the same trades on every non-gotobi Tokyo business day\n")
    print(f"{'period':20} {'trade':6} {'gotobi: n':>9} {'mean':>7} {'t':>6} {'win%':>6} | {'ordinary: n':>11} {'mean':>7} {'t':>6}")
    for per in ["2006-2015 (unseen)", "2016-2026", "all"]:
        sub = df if per == "all" else df[df.period == per]
        for leg in ["long", "short"]:
            g = sub[sub.gotobi][leg].dropna()
            o = sub[~sub.gotobi][leg].dropna()
            print(f"{per:20} {leg:6} {len(g):9} {g.mean():+7.2f} {tstat(g):6.2f} {(g > 0).mean():6.1%} | "
                  f"{len(o):11} {o.mean():+7.2f} {tstat(o):6.2f}")
        both = pd.concat([sub[sub.gotobi].long, sub[sub.gotobi].short]).dropna()
        print(f"{per:20} {'both':6} {len(both):9} {both.mean():+7.2f} {tstat(both):6.2f} {(both > 0).mean():6.1%}\n")

    # luck test: draw random sets of business days, as many as the gotobi days, and price the same two trades
    rng = np.random.default_rng(7)
    print("Luck test: 10,000 random sets of days, same size as the gotobi days, same two trades")
    for per in ["2006-2015 (unseen)", "2016-2026"]:
        sub = df[df.period == per]
        per_day = (sub.long.fillna(0) + sub.short.fillna(0)).to_numpy()
        real = per_day[sub.gotobi.to_numpy()].mean()
        n = int(sub.gotobi.sum())
        draws = np.array([per_day[rng.choice(len(per_day), n, replace=False)].mean() for _ in range(10_000)])
        print(f"  {per}: gotobi days {real:+.2f} pips/day; random sets average {draws.mean():+.2f}; "
              f"random beat gotobi {np.mean(draws >= real):.2%} of the time")

    print("\nEvery year, gotobi days, pips (long + short)")
    g = df[df.gotobi]
    yr = g.groupby("year").agg(long=("long", "sum"), short=("short", "sum"), days=("day", "count"))
    yr["total"] = yr.long + yr.short
    o = df[~df.gotobi].groupby("year")[["long", "short"]].mean().sum(axis=1)
    yr["ordinary day avg"] = o
    print(yr.round(1).to_string())
    print(f"\nyears with a gotobi profit: {(yr.total > 0).sum()} of {len(yr)}")

    lg = g.long.dropna()
    print(f"\nSwap: the long is held over the daily rollover. It stays profitable while its swap costs less than "
          f"{lg.mean():.1f} pips per trade (2006-2026 average gross of swap).")


if __name__ == "__main__":
    main()
