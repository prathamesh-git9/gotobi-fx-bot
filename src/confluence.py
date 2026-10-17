"""Multi-signal ("confluence") liquidity-sweep trades.

Every sweep+reclaim signal is recorded with a set of yes/no confluence checks, and its
outcome is simulated under several exit plans at once, so filter combinations can be
compared on identical trades:

  trend   daily trend agrees on two horizons (prior close vs 20- AND 50-day SMA)
  quick   the reclaim close comes within 3 five-minute candles of the first sweep
  shallow the sweep pokes past the level by at most 0.25x daily ATR (a stop run, not a breakout)
  strong  reclaim candle: body >= 50% of its range, closes in the outer third toward the trade
  mss     the reclaim close also breaks the 6-candle structure level (two confirmations at once)
  room    the opposite side of the pool is at least 2R away (the target has space)
  sane    stop distance between 0.05x and 0.4x daily ATR (not noise-tight, not huge)

Exit plans: 1.5R / 2R / 3R targets, each with and without moving the stop to break-even
once price has gone +1R in favour.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import TZ, day_levels, load

OUT = Path(__file__).resolve().parent.parent / "results"
WINDOWS = {"asia": (7, 10, 16), "pdhl": (7, 16, 20)}
EXITS = [(k, be) for k in (1.5, 2.0, 3.0) for be in (False, True)]
FILTERS = ["trend", "quick", "shallow", "strong", "mss", "room", "sane"]


def daily_context(df):
    g = df.groupby("lday")
    d = pd.DataFrame({"h": g["bh"].max(), "l": g["bl"].min(), "c": g["bc"].last(), "n": g.size()})
    d = d[d["n"] > 600]
    tr = np.maximum(d["h"] - d["l"], np.maximum((d["h"] - d["c"].shift()).abs(), (d["l"] - d["c"].shift()).abs()))
    ctx = pd.DataFrame({
        "atr": tr.rolling(14).mean(),
        "t20": np.sign(d["c"] - d["c"].rolling(20).mean()),
        "t50": np.sign(d["c"] - d["c"].rolling(50).mean()),
    })
    return ctx.shift(1).dropna()          # only yesterday's information is used today


def exit_r(m1, i0, side, entry, risk, k, be, flat_min):
    stop = entry - side * risk
    tp = entry + side * k * risk
    moved = False
    n = len(m1["bo"])
    for i in range(i0, n):
        if m1["lmin"][i] >= flat_min:
            px = m1["bo"][i] if side > 0 else m1["ao"][i]
            return (px - entry) * side / risk
        if side < 0:
            if m1["ah"][i] >= stop:
                return (entry - max(stop, m1["ao"][i])) / risk
            if m1["al"][i] <= tp:
                return k
            if be and not moved and m1["al"][i] <= entry - risk:
                stop, moved = entry, True       # takes effect from the next minute
        else:
            if m1["bl"][i] <= stop:
                return (min(stop, m1["bo"][i]) - entry) / risk
            if m1["bh"][i] >= tp:
                return k
            if be and not moved and m1["bh"][i] >= entry + risk:
                stop, moved = entry, True
    last = n - 1
    px = m1["bc"][last] if side > 0 else m1["ac"][last]
    return (px - entry) * side / risk


def first_reclaim(m5, hi, lo):
    o, h, l, c = (m5[x].to_numpy() for x in ("bo", "bh", "bl", "bc"))
    up = dn = None                       # (first sweep idx, extreme, extreme idx)
    for i in range(len(c)):
        if h[i] > hi:
            up = (i, h[i], i) if up is None else (up[0], max(up[1], h[i]), i if h[i] > up[1] else up[2])
        if l[i] < lo:
            dn = (i, l[i], i) if dn is None else (dn[0], min(dn[1], l[i]), i if l[i] < dn[1] else dn[2])
        for side, s in ((-1, up), (1, dn)):
            if s is None:
                continue
            if (side < 0 and c[i] < hi) or (side > 0 and c[i] > lo):
                first, ext, ext_i = s
                look = slice(max(0, ext_i - 6), ext_i)
                if side < 0:
                    ref = l[look].min() if ext_i > 0 else np.nan
                    mss = bool(c[i] < ref) if ext_i > 0 else False
                else:
                    ref = h[look].max() if ext_i > 0 else np.nan
                    mss = bool(c[i] > ref) if ext_i > 0 else False
                rng = h[i] - l[i]
                body = abs(c[i] - o[i])
                loc = (c[i] - l[i]) / rng if rng > 0 else 0.5
                strong = rng > 0 and body >= 0.5 * rng and (loc >= 2 / 3 if side > 0 else loc <= 1 / 3)
                depth = (ext - hi) if side < 0 else (lo - ext)
                return dict(side=side, i=i, ext=ext, quick=i - first <= 3, mss=mss, strong=strong, depth=depth)
    return None


def signals(sym, df=None):
    df = load(sym) if df is None else df
    ctx = daily_context(df)
    rows = []
    for model, (w0, w1, flat) in WINDOWS.items():
        levels = day_levels(df, model)
        for day, d in df.groupby("lday", sort=True):
            if day not in levels.index or day not in ctx.index:
                continue
            if model == "asia" and levels.at[day, "nbars"] < 300:
                continue
            hi, lo = levels.at[day, "hi"], levels.at[day, "lo"]
            sess = d[(d["lhour"] >= w0) & (d["lhour"] < flat)]
            if len(sess) < 60 or not (lo < sess["bo"].iat[0] < hi):
                continue
            win = sess[sess["lhour"] < w1]
            m5 = win[["bo", "bh", "bl", "bc"]].resample("5min").agg(
                {"bo": "first", "bh": "max", "bl": "min", "bc": "last"}).dropna()
            if len(m5) < 3:
                continue
            s = first_reclaim(m5, hi, lo)
            if s is None:
                continue
            i0 = sess.index.searchsorted(m5.index[s["i"]] + pd.Timedelta(minutes=5))
            m1 = {c: sess[c].to_numpy() for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "lmin")}
            if i0 >= len(sess) or m1["lmin"][i0] >= w1 * 60:
                continue
            side = s["side"]
            spread = m1["ao"][i0] - m1["bo"][i0]
            entry = m1["bo"][i0] if side < 0 else m1["ao"][i0]
            stop = s["ext"] + spread if side < 0 else s["ext"] - spread
            risk = (stop - entry) * side * -1
            if risk <= 0 or risk < 3 * spread:
                continue
            c = ctx.loc[day]
            room = ((entry - lo) if side < 0 else (hi - entry)) / risk
            row = dict(sym=sym, model=model, day=day, time=sess.index[i0], side=side, entry=entry,
                       risk=risk, spread_r=spread / risk, atr=c["atr"],
                       trend=bool(c["t20"] == side and c["t50"] == side),
                       quick=s["quick"], shallow=s["depth"] <= 0.25 * c["atr"], strong=s["strong"],
                       mss=s["mss"], room=room >= 2, sane=0.05 * c["atr"] <= risk <= 0.4 * c["atr"])
            for k, be in EXITS:
                row[f"r_{k}{'_be' if be else ''}"] = exit_r(m1, i0, side, entry, risk, k, be, flat * 60)
            rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    from concurrent.futures import ProcessPoolExecutor
    syms = sys.argv[1:] or ["XAUUSDm", "EURUSDm", "GBPUSDm", "USDJPYm"]
    with ProcessPoolExecutor(len(syms)) as ex:
        out = pd.concat(ex.map(signals, syms))
    out.to_parquet(OUT / "signals.parquet")
    print(out.groupby(["sym", "model"]).size())
