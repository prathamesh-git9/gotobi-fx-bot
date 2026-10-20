"""Round 5: liquidity sweeps where SMC traders actually use them, the New York open on NASDAQ / S&P / Dow, plus gold.
(The repo's first study tested 192 sweep variants on gold and FX at prior-day highs/lows; this covers the session
setups it did not.) Rules written BEFORE running; one fixed version each, no tuning.

A "sweep" of a level L (a high): an M5 bar trades above L, then within 3 bars an M5 bar CLOSES back below L, and
price never got accepted above L (no more than 2 M5 closes above L in the window so far). Sell at the next minute.
Stop = the highest price since the sweep began + the entry spread. Target 2R unless stated. Mirror for lows.
First signal of the day only; flat by the stated time. Real Exness bid/ask minutes, the stop wins ties.

 S1 Overnight-range sweep at the NY open: L = high/low of 18:00 (previous day) -> 09:30 NY; window 09:30-11:00 NY;
    flat 15:55 NY.
 S2 Previous-day high/low sweep: L = previous day's 09:30-16:00 NY high/low; window 09:30-12:00 NY; flat 15:55 NY.
 S3 Opening-range "Judas swing": L = 09:30-09:45 NY high/low; window 09:45-11:00 NY; target = the other side of the
    opening range (at least 1R); flat 15:55 NY.
 S4 Asia-range sweep at the London open (the classic gold setup): L = 00:00-06:00 UTC high/low; window 07:00-10:00
    UTC; flat 16:00 UTC.
Markets: USTEC (NASDAQ 100), US500, US30, XAUUSD. Index data start Aug 2019, gold 2016.
Pass: positive in both halves (to 2021 / from 2022), beats the same entries in a random direction, t > 2.8.

  python strategies/sweeps_ny/lab5.py
"""
import sys
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "different"))
import lab4  # noqa: E402
from lab4 import NY, M, load, mid_bars, report, run  # noqa: E402

lab4.PIP.update({"USTECm": 1.0, "US500m": 0.1, "US30m": 1.0, "XAUUSDm": 0.1})


def m5_local(df, tz):
    b = mid_bars(df, "5min")
    loc = b.index.tz_localize("UTC").tz_convert(tz)
    b["date"] = loc.date
    b["hm"] = loc.hour * 60 + loc.minute          # bar CLOSE time, local
    return b


def hm(s):
    h, m = map(int, s.split(":"))
    return h * 60 + m


def scan(win, hi_lvl, lo_lvl):
    """First sweep-and-reclaim in the window. Returns (k, side, extreme) with k the reclaim bar position."""
    h, lo, c = win.h.to_numpy(), win.l.to_numpy(), win.c.to_numpy()
    above = below = 0
    for k in range(len(win)):
        above += c[k] > hi_lvl
        below += c[k] < lo_lvl
        for side, lvl in ((-1, hi_lvl), (+1, lo_lvl)):
            if side < 0 and c[k] < lvl and above <= 2 and (h[max(0, k - 3):k + 1] > lvl).any():
                return k, -1, h[max(0, k - 3):k + 1].max()
            if side > 0 and c[k] > lvl and below <= 2 and (lo[max(0, k - 3):k + 1] < lvl).any():
                return k, +1, lo[max(0, k - 3):k + 1].min()
    return None


def setup(sym, kind):
    df = load(sym)
    m = M(df, lab4.PIP[sym])
    tz = "UTC" if kind == "S4" else NY
    b = m5_local(df, tz)
    del df
    days = sorted(set(b.date))
    by = {d: g for d, g in b.groupby("date")}
    sigs = []
    for n, d in enumerate(days[1:], 1):
        g, prev = by[d], by[days[n - 1]]
        if pd.Timestamp(d).weekday() >= 5:
            continue
        if kind == "S1":
            rng = pd.concat([prev[prev.hm > hm("18:00")], g[g.hm <= hm("09:30")]])
            w0, w1, flat = "09:30", "11:00", "15:55"
        elif kind == "S2":
            rng = prev[(prev.hm > hm("09:30")) & (prev.hm <= hm("16:00"))]
            w0, w1, flat = "09:30", "12:00", "15:55"
        elif kind == "S3":
            rng = g[(g.hm > hm("09:30")) & (g.hm <= hm("09:45"))]
            w0, w1, flat = "09:45", "11:00", "15:55"
        else:
            rng = g[(g.hm > 0) & (g.hm <= hm("06:00"))]
            w0, w1, flat = "07:00", "10:00", "16:00"
        if len(rng) < 3:
            continue
        H, L = rng.h.max(), rng.l.min()
        win = g[(g.hm > hm(w0)) & (g.hm <= hm(w1))]
        r = scan(win, H, L)
        if not r:
            continue
        k, side, ext = r
        t_sig = win.index[k]
        i = m.i(t_sig)
        fl = g[g.hm >= hm(flat)]
        if i is None or fl.empty:
            continue
        j = m.i(fl.index[0] - pd.Timedelta(minutes=5), tol=10)   # bar labelled by close -> its open minute
        e = m.aopen[i] if side > 0 else m.bopen[i]
        sp = m.aopen[i] - m.bopen[i]
        stop_d = (e - ext + sp) if side > 0 else (ext - e + sp)
        if stop_d < 3 * sp:                       # a stop inside 3 spreads is noise, not a sweep
            continue
        tp = 2 * stop_d
        if kind == "S3":
            tp = max(stop_d, (H - e) if side > 0 else (e - L))
        sigs.append((i, j, side, stop_d, tp, 0.0))
    return m, sigs


NAMES = {"S1": "overnight-range sweep at the NY open", "S2": "previous-day high/low sweep, NY morning",
         "S3": "opening-range Judas swing", "S4": "Asia-range sweep at the London open"}

if __name__ == "__main__":
    plan = [("S1", s) for s in ("USTECm", "US500m", "US30m", "XAUUSDm")] + \
           [("S2", s) for s in ("USTECm", "US500m", "US30m", "XAUUSDm")] + \
           [("S3", s) for s in ("USTECm", "US500m", "US30m")] + [("S4", "XAUUSDm"), ("S4", "USTECm")]
    for kind, sym in plan:
        m, sigs = setup(sym, kind)
        report(f"{kind} {sym[:-1]} {NAMES[kind]}", *run(m, sigs))
    import json
    (HERE / "lab5_results.json").write_text(json.dumps(lab4.OUT, indent=1, default=str))
