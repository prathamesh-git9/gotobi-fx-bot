"""High-win-rate gold strategies: buy short-term pullbacks inside the trend (and the short mirror).

Daily bars end at 16:00 New York (an hour before the 17:00 rollover, so spreads are normal).
Signals use the daily close; orders fill at the next minute's real Exness ask (long) / bid (short).

Families
  rsi2  Connors RSI(2): enter when RSI(2) < L (long) with close above SMA(T); exit when the close
        is back above SMA(5) ("sma5") or RSI(2) > 65 ("rsi65")
  lowN  close is the lowest close of the last N days, above SMA(T); exit on a close above the
        prior day's high ("pdh") or at an N-day closing high ("highN", the "double-7s" exit)
All trades: protective stop k x ATR(14) (also sets position size), max hold 10 days.

Costs per trade: real spread on entry and exit, $0.10/oz slippage, and overnight swap.
Swap is an assumption (Exness's gold swap varies): long pays 5.5%/yr of notional, short pays 1%/yr,
Wednesday counts triple. A swap-free figure is reported too.
"""
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
RES = DATA.parent / "results"
SLIP = 0.10
SWAP_LONG, SWAP_SHORT = 0.055, 0.01
MAX_HOLD = 10


def load_gold(files=("XAUUSDm_2015_m1.parquet", "XAUUSDm_m1.parquet")):
    parts = [pd.read_parquet(DATA / f) for f in files if (DATA / f).exists()]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    df.columns = [c[0] + c[1] if c[1:] in ("open", "high", "low", "close") else c for c in df.columns]
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    df["dkey"] = (ny + pd.Timedelta(hours=8)).date          # day ends 16:00 NY
    return df


def daily_bars(df):
    pos = pd.Series(np.arange(len(df)), index=df.index)
    g = df.groupby("dkey")
    d = pd.DataFrame({"o": g["bo"].first(), "h": g["bh"].max(), "l": g["bl"].min(), "c": g["bc"].last(),
                      "n": g.size(), "first_i": pos.groupby(df["dkey"].to_numpy()).first()})
    d = d[d["n"] > 600].copy()
    d["triple"] = [pd.Timestamp(x).weekday() == 3 for x in d.index]   # Wednesday rollover (x3 swap)
    delta = d["c"].diff()
    up = delta.clip(lower=0).ewm(alpha=0.5, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    d["rsi2"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    tr = np.maximum(d["h"] - d["l"], np.maximum((d["h"] - d["c"].shift()).abs(), (d["l"] - d["c"].shift()).abs()))
    d["atr"] = tr.rolling(14).mean()
    for t in (50, 100, 200):
        d[f"sma{t}"] = d["c"].rolling(t).mean()
    d["sma5"] = d["c"].rolling(5).mean()
    return d


def entries_exits(d, fam, p1, trend, ex):
    c = d["c"]
    above, below = c > d[f"sma{trend}"], c < d[f"sma{trend}"]
    if fam == "rsi2":
        long_in, short_in = (d["rsi2"] < p1) & above, (d["rsi2"] > 100 - p1) & below
        long_out = (c > d["sma5"]) if ex == "sma5" else (d["rsi2"] > 65)
        short_out = (c < d["sma5"]) if ex == "sma5" else (d["rsi2"] < 35)
    else:
        lo_n, hi_n = c.rolling(p1).min(), c.rolling(p1).max()
        long_in, short_in = (c <= lo_n) & above, (c >= hi_n) & below
        long_out = (c > d["h"].shift()) if ex == "pdh" else (c >= hi_n)
        short_out = (c < d["l"].shift()) if ex == "pdh" else (c <= lo_n)
    return long_in.to_numpy(), short_in.to_numpy(), long_out.to_numpy(), short_out.to_numpy()


def run(df, d, fam, p1, trend, ex, k, sides):
    li, si, lo, so = entries_exits(d, fam, p1, trend, ex)
    bid_l, ask_h = df["bl"].to_numpy(), df["ah"].to_numpy()
    bo, ao = df["bo"].to_numpy(), df["ao"].to_numpy()
    first_i, atr, days = d["first_i"].to_numpy(), d["atr"].to_numpy(), d.index
    triple = d["triple"].to_numpy()
    trades, i = [], 0
    while i < len(d) - 1:
        side = 1 if li[i] and "L" in sides else (-1 if si[i] and "S" in sides else 0)
        if side == 0 or np.isnan(atr[i]):
            i += 1
            continue
        e_i = first_i[i + 1]                          # first minute after the signal close
        entry = ao[e_i] if side > 0 else bo[e_i]
        risk = k * atr[i]
        stop = entry - side * risk
        exit_day = None
        for j in range(i + 1, min(i + 1 + MAX_HOLD, len(d) - 1)):
            if (lo[j] if side > 0 else so[j]):
                exit_day = j
                break
        if exit_day is None:
            exit_day = min(i + MAX_HOLD, len(d) - 2)
        x_i = first_i[exit_day + 1]
        seg = slice(e_i, x_i)
        hit = np.where(bid_l[seg] <= stop)[0] if side > 0 else np.where(ask_h[seg] >= stop)[0]
        if len(hit):
            m = e_i + hit[0]
            op = bo[m] if side > 0 else ao[m]
            px = min(stop, op) if side > 0 else max(stop, op)
            x_i, reason = m, "stop"
        else:
            px = bo[x_i] if side > 0 else ao[x_i]
            reason = "signal"
        # each day key holds one 17:00 NY rollover; the position pays for every key it lives through
        k_exit = int(np.searchsorted(first_i, x_i, side="right")) - 1     # key containing the exit minute
        if reason == "signal":
            k_exit -= 1                                                   # exits at that key's first minute
        nights = int(sum(3 if triple[q] else 1 for q in range(i + 1, k_exit + 1)))
        swap = entry * (SWAP_LONG if side > 0 else SWAP_SHORT) / 360 * nights
        gross = (px - entry) * side
        net = gross - SLIP - swap
        trades.append(dict(day=days[i], side=side, entry=entry, exit=px, risk=risk, nights=nights,
                           gross_r=gross / risk, r=net / risk, r_noswap=(gross - SLIP) / risk,
                           ret=gross / entry, reason=reason,
                           hold=exit_day - i))
        i = exit_day + 1 if reason == "signal" else int(np.searchsorted(first_i, x_i, side="right"))
    return pd.DataFrame(trades)


GRID = ([("rsi2", L, T, ex, k, s) for L, T, ex, k, s in product([5, 10, 15, 20, 25], [50, 100, 200],
                                                                  ["sma5", "rsi65"], [2, 3], ["L", "LS"])] +
        [("lowN", N, T, ex, k, s) for N, T, ex, k, s in product([3, 5, 7], [50, 100, 200],
                                                                 ["pdh", "highN"], [2, 3], ["L", "LS"])])
