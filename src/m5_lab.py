"""Gold 5-minute signal lab: high-win-rate intraday rules, never holding through the 17:00 NY rollover.

Families (signal on a closed 5-min mid candle, entry at the next candle's open):
  mr_rsi   RSI(3) below L (long) / above 100-L (short)            -> fade the stretch
  mr_bb    close outside the 20-bar Bollinger band (2.5 sd)       -> fade the stretch
  hour     enter at the top of a given New York hour, long or short (intraday seasonality)
  orb      New York opening range (08:00-08:30) breakout, 08:30-11:00
Optional filters: session (asia 18-03 / london 03-08 / ny 08-12 / any), trend (price vs 20-day EMA).
Exits: take-profit tp x ATR(14, M5), stop sl x ATR, time stop after H candles, and always out by 16:55 NY.
Inside one candle the stop beats the target. A stop gapped through fills at the candle open.

Two cost models, charged once per trade:
  actual  the real Exness Standard spread at entry + $0.10/oz slippage
  modern  today's spread (0.007% of price) + $0.10/oz slippage. Signals are judged on this across
          all years, so a rule isn't rejected only because 2016's spreads were 5x wider.
"""
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

from high_wr import load_gold

RES = Path(__file__).resolve().parent.parent / "results"
SLIP, MODERN = 0.10, 0.00007
TPS, SLS, HS = [0.5, 1.0], [1.0, 2.0, 3.0], [6, 12, 24]


def m5_bars():
    df = load_gold()
    mid = pd.DataFrame({"o": (df.bo + df.ao) / 2, "h": (df.bh + df.ah) / 2, "l": (df.bl + df.al) / 2,
                        "c": (df.bc + df.ac) / 2, "sp": df.ao - df.bo})
    m = mid.resample("5min").agg({"o": "first", "h": "max", "l": "min", "c": "last", "sp": "first"}).dropna()
    ny = m.index.tz_localize("UTC").tz_convert("America/New_York")
    m["nyh"] = ny.hour
    m["nymin"] = ny.hour * 60 + ny.minute
    m["wd"] = ny.weekday
    tr = np.maximum(m.h - m.l, np.maximum((m.h - m.c.shift()).abs(), (m.l - m.c.shift()).abs()))
    m["atr"] = tr.rolling(14).mean()
    d = m.c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 3, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 3, adjust=False).mean()
    m["rsi3"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    mu, sd = m.c.rolling(20).mean(), m.c.rolling(20).std()
    m["bb_lo"], m["bb_hi"] = mu - 2.5 * sd, mu + 2.5 * sd
    m["ema20d"] = m.c.ewm(span=288 * 20, adjust=False).mean()
    # last bar index allowed before the 16:55 NY cutoff (positions, so gaps are respected)
    cut = (ny.normalize() + pd.Timedelta(hours=16, minutes=55))
    cut = cut.where(ny <= cut, cut + pd.Timedelta(days=1))
    m["cut_i"] = np.searchsorted(ny.values, cut.values, side="right") - 1
    # NY opening range
    day = ny.date
    orw = (m.nymin >= 480) & (m.nymin < 510)
    g = m[orw].groupby(day[orw.to_numpy()])
    m["or_hi"] = pd.Series(day, index=m.index).map(g.h.max())
    m["or_lo"] = pd.Series(day, index=m.index).map(g.l.min())
    return m


def session_mask(m, s):
    h = m.nyh
    return {"asia": (h >= 18) | (h < 3), "london": (h >= 3) & (h < 8), "ny": (h >= 8) & (h < 12),
            "any": (h < 16) | (h >= 18)}[s].to_numpy()


def simulate(m, sig_i, side, tp, sl, H, cost_model):
    """Vectorized outcomes for signals at bar positions sig_i (entry at the next bar's open)."""
    n = len(m)
    o, h, l, c = (m[x].to_numpy() for x in ("o", "h", "l", "c"))
    atr, cut_i, sp = m.atr.to_numpy(), m.cut_i.to_numpy(), m.sp.to_numpy()
    e = sig_i + 1
    ok = (e < n - H - 1) & ~np.isnan(atr[sig_i]) & (cut_i[sig_i] > e)
    sig_i, e = sig_i[ok], e[ok]
    side = side[ok] if np.ndim(side) else np.full(len(e), side)
    last = np.minimum(e + H - 1, cut_i[sig_i])
    entry = o[e]
    risk = sl * atr[sig_i]
    stop = entry - side * risk
    tgt = entry + side * tp * atr[sig_i]
    win = np.arange(H)[None, :]
    idx = np.minimum(e[:, None] + win, n - 1)
    valid = idx <= last[:, None]
    hh, ll, oo = h[idx], l[idx], o[idx]
    s_side = side[:, None]
    hit_s = valid & np.where(s_side > 0, ll <= stop[:, None], hh >= stop[:, None])
    hit_t = valid & np.where(s_side > 0, hh >= tgt[:, None], ll <= tgt[:, None])
    fs = np.where(hit_s.any(1), hit_s.argmax(1), H + 1)
    ft = np.where(hit_t.any(1), hit_t.argmax(1), H + 1)
    rows = np.arange(len(e))
    px = c[last]
    xi = last.copy()
    stop_first = (fs <= ft) & (fs <= H)
    op = oo[rows, np.minimum(fs, H - 1)]
    px = np.where(stop_first, np.where(side > 0, np.minimum(stop, op), np.maximum(stop, op)), px)
    xi = np.where(stop_first, e + fs, xi)
    tgt_first = (ft < fs) & (ft <= H)
    px = np.where(tgt_first, tgt, px)
    xi = np.where(tgt_first, e + ft, xi)
    cost = (sp[e] if cost_model == "actual" else MODERN * entry) + SLIP
    r = ((px - entry) * side - cost) / risk
    return pd.DataFrame({"i": sig_i, "e": e, "x": xi, "side": side, "r": r, "risk": risk, "entry": entry})


def non_overlap(t):
    keep, busy = [], -1
    for row in t.itertuples(index=False):
        if row.e > busy:
            keep.append(True)
            busy = row.x
        else:
            keep.append(False)
    return t[np.array(keep, bool)] if len(t) else t


def signals(m, fam, p, sess, trend):
    c = m.c.to_numpy()
    base = session_mask(m, sess) & ~((m.wd == 4) & (m.nyh >= 15)).to_numpy()
    up = (m.c > m.ema20d).to_numpy()
    if fam == "mr_rsi":
        L = p
        long_, short_ = m.rsi3.to_numpy() < L, m.rsi3.to_numpy() > 100 - L
    elif fam == "mr_bb":
        long_, short_ = c < m.bb_lo.to_numpy(), c > m.bb_hi.to_numpy()
    elif fam == "hour":
        hit = (m.nymin == p * 60).to_numpy()
        return np.flatnonzero(hit & ((m.nyh < 16) | (m.nyh >= 18)).to_numpy() & ~((m.wd == 4) & (m.nyh >= 15)).to_numpy())
    else:  # orb: first close beyond the NY opening range, 08:30-11:00
        win = ((m.nymin >= 510) & (m.nymin < 660)).to_numpy()
        long_, short_ = win & (c > m.or_hi.to_numpy()), win & (c < m.or_lo.to_numpy())
        day = (m.index.tz_localize("UTC").tz_convert("America/New_York").normalize()).values
        first = pd.Series(long_ | short_).groupby(day).cumsum().to_numpy() == 1   # first breakout of the day
        long_, short_ = long_ & first, short_ & first
        base = np.ones(len(m), bool)
    if trend == "with":
        long_, short_ = long_ & up, short_ & ~up
    elif trend == "against":
        long_, short_ = long_ & ~up, short_ & up
    return np.flatnonzero(base & long_), np.flatnonzero(base & short_)


def configs():
    for fam, p, sess, trend, sides in product(["mr_rsi"], [5, 10, 15], ["asia", "london", "ny", "any"],
                                              ["none", "with"], ["L", "S", "LS"]):
        yield fam, p, sess, trend, sides
    for sess, trend, sides in product(["asia", "london", "ny", "any"], ["none", "with"], ["L", "S", "LS"]):
        yield "mr_bb", 0, sess, trend, sides
    for hr, sides in product([x for x in range(24) if x not in (16, 17)], ["L", "S"]):
        yield "hour", hr, "any", "none", sides
    for trend, sides in product(["none", "with", "against"], ["L", "S", "LS"]):
        yield "orb", 0, "ny", trend, sides


def run_config(m, cfg, tp, sl, H, cost_model):
    fam, p, sess, trend, sides = cfg
    if fam == "hour":
        si = signals(m, fam, p, sess, trend)
        side = 1 if sides == "L" else -1
        t = simulate(m, si, side, tp, sl, H, cost_model)
    else:
        li, sh = signals(m, fam, p, sess, trend)
        parts = []
        if "L" in sides:
            parts.append((li, 1))
        if "S" in sides:
            parts.append((sh, -1))
        idx = np.concatenate([x for x, _ in parts]) if parts else np.array([], int)
        sd = np.concatenate([np.full(len(x), s) for x, s in parts]) if parts else np.array([])
        order = np.argsort(idx, kind="stable")
        t = simulate(m, idx[order], sd[order], tp, sl, H, cost_model)
    t = non_overlap(t.sort_values("e"))
    t["time"] = m.index.values[t.e.to_numpy()]
    return t
