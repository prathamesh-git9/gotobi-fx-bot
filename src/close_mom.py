"""Into-the-close momentum: does the day's move continue over the last 30 minutes before the official close?

Published effect, settings taken from the papers, nothing tuned here:
  Gao, Han, Li & Zhou (2018) "Market intraday momentum", JFE        (S&P 500, 1993-2013)
  Baltussen, Da, Lammers & Martens (2021) "Hedging demand and market intraday momentum", JFE
      (60+ futures, 1974-2020; cause: option dealers' gamma hedging and leveraged-ETF rebalancing
       push in the direction of the day's move into the close)

Rule, per market and trading day:
  signal  = return from the previous official close to 30 minutes before today's close
            (last tick before each time, mid price)
  trade   = at close-30m buy if the signal is up, sell if down (market order, real bid/ask);
            exit with the last tick before the close. No stop, no target, never held overnight
            (no financing). Variant "gao": signal = previous close -> first 30 minutes of the session.
Costs: the real Exness Standard bid/ask at entry and exit, plus slippage of 0.2 bp per side.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
RES = DATA.parent / "results"
SLIP = 0.2e-4

# market: (file, timezone, session open, official close, calendar from Yahoo, early-close rule)
MARKETS = {
    "US500": ("US500m_m1.parquet", "America/New_York", "09:30", "16:00", "SPY", "us"),
    "US30": ("US30m_m1.parquet", "America/New_York", "09:30", "16:00", "SPY", "us"),
    "USTEC": ("USTECm_m1.parquet", "America/New_York", "09:30", "16:00", "SPY", "us"),
    "DE30": ("DE30m_m1.parquet", "Europe/Berlin", "09:00", "17:30", "^GDAXI", "none"),
    "UK100": ("UK100m_m1.parquet", "Europe/London", "08:00", "16:30", "^FTSE", "uk"),
    "XAUUSD": (("XAUUSDm_2015_m1.parquet", "XAUUSDm_m1.parquet"), "America/New_York", "08:20", "13:30", "SPY", "us"),
    "EURUSD": ("EURUSDm_m1.parquet", "Europe/London", "08:00", "16:00", "EURUSD=X", "uk"),
    "GBPUSD": ("GBPUSDm_m1.parquet", "Europe/London", "08:00", "16:00", "GBPUSD=X", "uk"),
    "USDJPY": ("USDJPYm_m1.parquet", "Europe/London", "08:00", "16:00", "USDJPY=X", "uk"),
}


def load_m1(files):
    files = files if isinstance(files, tuple) else (files,)
    parts = [pd.read_parquet(DATA / f, columns=["bopen", "bclose", "aopen", "aclose"]) for f in files
             if (DATA / f).exists()]
    df = pd.concat(parts).sort_index()
    return df[~df.index.duplicated()]


def early_close(dates, rule):
    d = pd.DatetimeIndex(dates)
    if rule == "us":   # 13:00 closes: day after Thanksgiving, Dec 24, Jul 3
        thanks = (d.month == 11) & (d.weekday == 4) & (d.day >= 23) & (d.day <= 29)
        return thanks | ((d.month == 12) & (d.day == 24)) | ((d.month == 7) & (d.day == 3))
    if rule == "uk":   # 12:30 closes
        return (d.month == 12) & ((d.day == 24) | (d.day == 31))
    return np.zeros(len(d), bool)


def trading_days(cal_sym, rule):
    y = pd.read_parquet(DATA / "daily_yahoo.parquet", columns=["date", "sym"])
    days = pd.DatetimeIndex(sorted(pd.to_datetime(y[y.sym == cal_sym].date).dt.tz_localize(None).dt.normalize().unique()))
    days = days[days.weekday < 5]
    return days[~early_close(days, rule)]


def build(name, back=30):
    files, tz, sopen, close, cal, rule = MARKETS[name]
    df = load_m1(files)
    t_utc = df.index.values.astype("datetime64[ns]")
    days = trading_days(cal, rule)
    days = days[(days >= df.index[0].normalize()) & (days <= df.index[-1].normalize())]

    def at(hm, back=0):
        """UTC datetime64 of local date + hh:mm for every trading day."""
        loc = (days + pd.Timedelta(hm + ":00") - pd.Timedelta(minutes=back)).tz_localize(tz, nonexistent="shift_forward",
                                                                                          ambiguous="NaT")
        return loc.tz_convert("UTC").tz_localize(None).values.astype("datetime64[ns]")

    def last_before(T, stale=5):
        i = np.searchsorted(t_utc, T, side="left") - 1
        ok = (i >= 0) & ((T - t_utc[np.clip(i, 0, None)]) <= np.timedelta64(stale, "m"))
        return np.clip(i, 0, None), ok

    def first_after(T, late=2):
        i = np.searchsorted(t_utc, T, side="left")
        i2 = np.clip(i, 0, len(t_utc) - 1)
        ok = (i < len(t_utc)) & ((t_utc[i2] - T) <= np.timedelta64(late, "m"))
        return i2, ok

    mid_c = ((df.bclose + df.aclose) / 2).to_numpy()
    bo, ao, bc, ac = (df[c].to_numpy() for c in ("bopen", "aopen", "bclose", "aclose"))
    T_close, T_entry = at(close), at(close, back=back)
    o_h, o_m = map(int, sopen.split(":"))
    T_first = at(f"{o_h + (o_m + 30) // 60:02d}:{(o_m + 30) % 60:02d}")
    i_close, ok_c = last_before(T_close)
    i_sig, ok_s = last_before(T_entry)
    i_first, ok_f = last_before(T_first)
    i_ent, ok_e = first_after(T_entry)
    ok = ok_c & ok_s & ok_e & ok_f
    t = pd.DataFrame({"day": days, "close_mid": mid_c[i_close], "sig_mid": mid_c[i_sig], "first_mid": mid_c[i_first],
                      "ent_bid": bo[i_ent], "ent_ask": ao[i_ent], "ex_bid": bc[i_close], "ex_ask": ac[i_close], "ok": ok})
    t["prev_close"] = t.close_mid.shift(1).where(t.ok.shift(1, fill_value=False))
    t = t[t.ok & t.prev_close.notna()].copy()
    t["rod"] = t.sig_mid / t.prev_close - 1             # rest-of-day signal (Baltussen)
    t["fh"] = t.first_mid / t.prev_close - 1            # first half-hour signal (Gao)
    mid_e = (t.ent_bid + t.ent_ask) / 2
    t["last30"] = ((t.ex_bid + t.ex_ask) / 2) / mid_e - 1            # mid-to-mid, no costs
    t["spread_rt"] = (t.ent_ask - t.ent_bid) / mid_e / 2 + (t.ex_ask - t.ex_bid) / ((t.ex_bid + t.ex_ask) / 2) / 2
    for sig in ("rod", "fh"):
        side = np.sign(t[sig])
        long_r = t.ex_bid / t.ent_ask - 1
        short_r = 1 - t.ex_ask / t.ent_bid
        t[f"net_{sig}"] = np.where(side > 0, long_r, np.where(side < 0, short_r, 0.0)) - 2 * SLIP
        t[f"gross_{sig}"] = side * t.last30
    t["sym"] = name
    return t


def summary(t, col):
    r = t[col]
    return dict(n=len(r), hit=(r > 0).mean(), bp=r.mean() * 1e4, t=r.mean() / r.std() * np.sqrt(len(r)),
                sharpe=r.mean() / r.std() * np.sqrt(252))


if __name__ == "__main__":
    names = sys.argv[1:] or [m for m in MARKETS if (DATA / (MARKETS[m][0] if isinstance(MARKETS[m][0], str)
                                                             else MARKETS[m][0][-1])).exists()]
    out, lines = [], []

    def p(s=""):
        print(s, flush=True)
        lines.append(s)

    for name in names:
        t = build(name)
        out.append(t)
        y = t.day.dt.year
        p(f"\n=== {name}  {t.day.min().date()} -> {t.day.max().date()}  days {len(t)}  "
          f"median round-trip spread {t.spread_rt.median() * 1e4:.2f} bp  avg |last 30m| {t.last30.abs().mean() * 1e4:.1f} bp")
        p(f"  always-long last 30m (drift): {t.last30.mean() * 1e4:+.2f} bp/day")
        for sig, lab in (("rod", "Baltussen: prev close -> close-30m"), ("fh", "Gao: prev close -> first 30m")):
            g, n = summary(t, f"gross_{sig}"), summary(t, f"net_{sig}")
            p(f"  {lab}: gross {g['bp']:+.2f} bp (t {g['t']:+.2f}, hit {g['hit']:.1%})  |  "
              f"net {n['bp']:+.2f} bp (t {n['t']:+.2f}, hit {n['hit']:.1%}, Sharpe {n['sharpe']:+.2f})")
            up, dn = t[t[sig] > 0], t[t[sig] < 0]
            p(f"      up-signal days {len(up)}: net {up[f'net_{sig}'].mean() * 1e4:+.2f} bp | "
              f"down-signal days {len(dn)}: net {dn[f'net_{sig}'].mean() * 1e4:+.2f} bp")
            big = t[t[sig].abs() > t[sig].abs().rolling(250, min_periods=100).median().shift(1)]
            p(f"      bigger-than-usual signal days {len(big)}: net {big[f'net_{sig}'].mean() * 1e4:+.2f} bp "
              f"(t {summary(big, f'net_{sig}')['t']:+.2f})")
            p("      by year (net bp): " + " ".join(f"{yy % 100:02d}:{v * 1e4:+.1f}" for yy, v in
                                                t.groupby(y)[f"net_{sig}"].mean().items()))
    allt = pd.concat(out)
    allt.to_parquet(RES / "close_mom_trades.parquet")
    (RES / f"close_mom_report_{'_'.join(names)}.txt").write_text("\n".join(lines), encoding="utf-8")
