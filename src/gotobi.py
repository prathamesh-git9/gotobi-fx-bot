"""Gotobi anomaly backtest: USD/JPY into the 09:55 JST Tokyo fix on days ending in 0 or 5.

Mechanism: Japanese importers settle dollar invoices on gotobi days (5, 10, 15, 20, 25, 30); banks buy USD
into the 09:55 JST fix. Ito & Yamada (J. Int. Econ. 2017) document dollar-biased order flow before the fix.

Rule tested exactly as given to us (window A), plus three fixed alternatives, all reported:
  A  long  00:55 -> 09:55 JST (15:55 -> 00:55 UTC, crosses the 17:00 NY rollover)   <- the pasted rule
  B  long  14:00 JST previous day -> 09:55 JST                                          (TradingView script)
  C  long  08:00 -> 09:55 JST (23:00 -> 00:55 UTC, no rollover)                         (pre-fix flow only)
  D  short 09:55 -> 11:00 JST (00:55 -> 02:00 UTC)                                      (post-fix fade)
Gotobi day: 5/10/15/20/25/30; a weekend gotobi moves to the Friday before ('jp' variant also moves it off
Japanese public holidays). Control: the same window on every other business day.
Fills: real Exness Standard bid/ask, first tick at/after each time, + 0.2 bp slippage per side. If the entry time
falls in a market closure (Sunday), entry is 15 minutes after the reopen. Catastrophic stop 55 pips.
Swap (windows that cross 17:00 NY): long earns (USD rate - JPY rate - 1% broker markup)/360 per night,
x3 on Wednesday nights; reported separately because it depends on the account (Exness swap-free accounts pay 0).
"""
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
RES = DATA.parent / "results"
SLIP = 0.2e-4
STOP_PIPS = 55
MARKUP = 0.01
WINDOWS = {  # name: (entry offset before/after the 00:55 UTC fix, exit offset, side)
    "A": (-pd.Timedelta(hours=9), pd.Timedelta(0), 1),
    "B": (-pd.Timedelta(hours=19, minutes=55), pd.Timedelta(0), 1),
    "C": (-pd.Timedelta(hours=1, minutes=55), pd.Timedelta(0), 1),
    "D": (pd.Timedelta(0), pd.Timedelta(hours=1, minutes=5), -1),
}


def load():
    files = ["USDJPYm_2016_m1.parquet", "USDJPYm_m1.parquet", "USDJPYm_2026_10_m1.parquet"]
    parts = [pd.read_parquet(DATA / f, columns=["bopen", "blow", "bhigh", "aopen", "alow", "ahigh"])
             for f in files if (DATA / f).exists()]
    df = pd.concat(parts).sort_index()
    return df[~df.index.duplicated()]


def gotobi_dates(start, end, jp_holidays=False):
    jp = holidays.Japan(years=range(start.year, end.year + 1))
    out = set()
    for m in pd.period_range(start, end, freq="M"):
        for d in (5, 10, 15, 20, 25, 30):
            if d > m.days_in_month:
                continue
            day = pd.Timestamp(m.year, m.month, d)
            while day.weekday() >= 5 or (jp_holidays and day.date() in jp):
                day -= pd.Timedelta(days=1)
            out.add(day)
    return pd.DatetimeIndex(sorted(x for x in out if start <= x <= end))


def rate_series(start, end):
    y = pd.read_parquet(DATA / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    usd = y[y.sym == "^IRX"].set_index(pd.to_datetime(y[y.sym == "^IRX"].date).dt.tz_localize(None).dt.normalize()).close / 100
    idx = pd.date_range(start, end, freq="D")
    usd = usd.reindex(idx).ffill().bfill()
    jpy = pd.Series(-0.001, index=idx)
    jpy[idx >= "2024-03-19"] = 0.0005
    jpy[idx >= "2024-07-31"] = 0.0025
    jpy[idx >= "2025-01-24"] = 0.005
    return usd - jpy


def trades(df, days, win, diff):
    off_in, off_out, side = WINDOWS[win]
    t = df.index.values
    bo, ao, bl, ah = (df[c].to_numpy() for c in ("bopen", "aopen", "blow", "ahigh"))
    fix = days + pd.Timedelta(minutes=55)                      # 09:55 JST = 00:55 UTC, same date
    T_in, T_out = (fix + off_in).values, (fix + off_out).values
    i_in = np.searchsorted(t, T_in, side="left")
    i_out = np.searchsorted(t, T_out, side="left")
    rows = []
    for k in range(len(days)):
        a, b = i_in[k], i_out[k]
        if a >= len(t) or b >= len(t):
            continue
        late = t[a] - T_in[k] > np.timedelta64(30, "m")
        if late:                                               # market was shut: enter 15 min after reopen
            a = np.searchsorted(t, t[a] + np.timedelta64(15, "m"), side="left")
        if t[b] - T_out[k] > np.timedelta64(5, "m") or b <= a:
            continue
        ent = ao[a] if side > 0 else bo[a]
        mid_in, mid_out = (ao[a] + bo[a]) / 2, (ao[b] + bo[b]) / 2
        stop = ent - side * STOP_PIPS / 100
        seg = bl[a:b] if side > 0 else ah[a:b]
        hit = np.flatnonzero(seg <= stop) if side > 0 else np.flatnonzero(seg >= stop)
        if len(hit):
            j = a + hit[0]
            o = bo[j] if side > 0 else ao[j]
            ex = min(stop, o) if side > 0 else max(stop, o)
            reason = "stop"
            t_exit = t[j]
        else:
            ex = bo[b] if side > 0 else ao[b]
            reason = "time"
            t_exit = t[b]
        slip = 2 * SLIP * mid_in
        net = (ex - ent) * side - slip
        # rollovers crossed (17:00 New York), Wednesday counts 3
        ts_in, ts_out = pd.Timestamp(t[a]), pd.Timestamp(t[b])
        nights = 0
        for dd in pd.date_range(ts_in.normalize() - pd.Timedelta(days=1), ts_out.normalize(), freq="D"):
            ro = pd.Timestamp(dd.date()).tz_localize("America/New_York") + pd.Timedelta(hours=17)
            ro = ro.tz_convert("UTC").tz_localize(None)
            if ts_in < ro <= ts_out and ro.weekday() < 5:
                nights += 3 if ro.weekday() == 2 else 1
        swap_pips = side * diff.get(days[k].normalize(), 0.0) * nights / 360 * mid_in * 100 if nights else 0.0
        if side > 0:
            swap_pips = side * (diff.get(days[k].normalize(), 0.0) - MARKUP) * nights / 360 * mid_in * 100
        else:
            swap_pips = -(diff.get(days[k].normalize(), 0.0) + MARKUP) * nights / 360 * mid_in * 100 if nights else 0.0
        rows.append(dict(day=days[k], wd=days[k].weekday(), gross=(mid_out - mid_in) * side * 100, net=net * 100,
                         swap=swap_pips, spread=(ao[a] - bo[a]) * 100 + (ao[b] - bo[b]) * 100, reason=reason,
                         late_entry=late, price=mid_in, t_in=pd.Timestamp(t[a]), t_out=pd.Timestamp(t_exit),
                         ent=ent, ex=ex, side=side))
    return pd.DataFrame(rows)


def summ(x, col="net"):
    r = x[col]
    if len(r) < 5:
        return dict(n=len(r))
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    return dict(n=len(r), win=(r > 0).mean(), avg=r.mean(), t=r.mean() / r.std() * np.sqrt(len(r)),
                pf=wins / losses if losses > 0 else np.inf)


def welch(a, b):
    return (a.mean() - b.mean()) / np.sqrt(a.var() / len(a) + b.var() / len(b))


def account(x, col, risk=0.01, start=100.0):
    bal, peak, dd = start, start, 0.0
    for r in x[col]:
        bal *= 1 + risk * r / STOP_PIPS
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    return bal, dd


if __name__ == "__main__":
    df = load()
    start, end = df.index[0].normalize() + pd.Timedelta(days=2), df.index[-1].normalize() - pd.Timedelta(days=1)
    diff = rate_series(start - pd.Timedelta(days=5), end + pd.Timedelta(days=5)).to_dict()
    bdays = pd.bdate_range(start, end)
    lines = []

    def p(s=""):
        print(s, flush=True)
        lines.append(s)

    p(f"USD/JPY Exness Standard ticks {df.index[0].date()} -> {df.index[-1].date()}")
    out = {}
    for variant, jp in (("pasted rule (weekend -> Friday)", False), ("+ Japanese holidays moved too", True)):
        g_days = gotobi_dates(start, end, jp)
        c_days = bdays[~bdays.isin(g_days)]
        p(f"\n##### Gotobi days: {variant}: {len(g_days)} gotobi days, {len(c_days)} control days")
        for win in ("A", "B", "C", "D") if not jp else ("A", "C"):
            g, c = trades(df, g_days, win, diff), trades(df, c_days, win, diff)
            out[(variant, win)] = (g, c)
            off_in, off_out, side = WINDOWS[win]
            p(f"\n=== Window {win} ({'long' if side > 0 else 'short'}; entry fix{off_in}, exit fix+{off_out})")
            for lab, x in (("GOTOBI", g), ("control (all other days)", c)):
                s, sg = summ(x, "net"), summ(x, "gross")
                p(f"  {lab:25s} n {s['n']:4d}  gross {sg['avg']:+.2f} pips (t {sg['t']:+.2f})  net {s['avg']:+.2f} pips "
                  f"(t {s['t']:+.2f}, win {s['win']:.1%}, PF {s['pf']:.2f})  swap {x.swap.mean():+.2f} pips  "
                  f"stops {np.mean(x.reason == 'stop'):.1%}")
            p(f"  gotobi minus control (gross): {g.gross.mean() - c.gross.mean():+.2f} pips, Welch t {welch(g.gross, c.gross):+.2f}")
            for lab, a, b in (("2016-2018 (never used by the claim)", "2016", "2019"), ("2019-2021", "2019", "2022"),
                              ("2022-2026 (the claim's out-of-sample)", "2022", "2027")):
                gg, cc = g[(g.day >= a) & (g.day < b)], c[(c.day >= a) & (c.day < b)]
                if len(gg) < 10:
                    continue
                s = summ(gg, "net")
                bal, dd = account(gg, "net")
                bal2, dd2 = account(gg.assign(ns=gg.net + gg.swap), "ns")
                p(f"    {lab:38s} gotobi n {s['n']:3d} net {s['avg']:+.2f} pips (t {s['t']:+.2f}, PF {s['pf']:.2f}) | "
                  f"control net {cc.net.mean():+.2f} | diff {gg.gross.mean() - cc.gross.mean():+.2f} (t {welch(gg.gross, cc.gross):+.2f})"
                  f" | 1% risk: {(bal / 100 - 1):+.1%} (DD {dd:.1%}), with swap {(bal2 / 100 - 1):+.1%}")
            yr = pd.DataFrame({"gotobi net": g.groupby(g.day.dt.year).net.mean(),
                               "control net": c.groupby(c.day.dt.year).net.mean(),
                               "diff gross": g.groupby(g.day.dt.year).gross.mean() - c.groupby(c.day.dt.year).gross.mean(),
                               "n": g.groupby(g.day.dt.year).size()})
            p("    by year (pips): " + "  ".join(f"{y % 100:02d}: G {r['gotobi net']:+.1f} C {r['control net']:+.1f}"
                                                 for y, r in yr.iterrows()))
    pd.to_pickle(out, RES / "gotobi_trades.pkl")
    (RES / "gotobi_report.txt").write_text("\n".join(lines), encoding="utf-8")
