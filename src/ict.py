"""Sweep -> displacement -> order-block entry, with order-flow and liquidity-heat-map signals.

Setup (bearish shown; bullish is the mirror):
  1. Sweep    bid trades above the pool high (Asian high or previous-day high).
  2. Shift    a 5-min candle closes below the low of the 6 candles before the sweep extreme
              (market-structure shift / displacement).
  3. OB       the order block is the last up-close candle at or before the sweep extreme.
              Entry is a SELL LIMIT at its mean threshold (50% of the body). It's valid until the
              window closes, and cancelled if price reaches the target or the stop before filling.
              A market entry at the shift close is also recorded so the OB's value can be measured.
  4. Stop above max(sweep extreme, OB high) + spread. Targets 2R / 3R / 3R with break-even / pool opposite.

Signals recorded per setup (all known at order time, nothing from the future):
  fvg        the displacement leg left a fair-value gap (3-candle imbalance)
  of_spike   tick volume on the sweep-extreme candle >= 1.5x the median of the prior 24 candles
  of_absorb  on that candle, tick delta leaned WITH the sweep (buyers chasing the high) by >=10%:
             aggressive orders absorbed and trapped
  of_disp    the shift candle's tick delta leans with the trade by >=10% (aggressive sellers)
  heat       the sweep cleared >= 2 untouched M15 swing highs from the last week (stacked stops)
  magnet     an untouched opposite swing sits between entry and the 3R target (liquidity to draw price)
  trend      prior close beyond both its 20- and 50-day SMA in the trade direction
  sane       stop distance 0.05x - 0.4x daily ATR

Tick delta comes from the tick rule on the Exness mid price (spot FX/gold has no exchange
volume, so this is the standard approximation, not true order flow).
"""
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import day_levels, load
from confluence import daily_context

OUT = Path(__file__).resolve().parent.parent / "results"
WINDOWS = {"asia": (7, 10, 16), "pdhl": (7, 16, 20)}
TARGETS = ["2", "3", "3be", "range"]


def fractals(df):
    """M15 swing highs/lows, when they became known, and when price first traded through them."""
    m15 = df[["bh", "bl"]].resample("15min").agg({"bh": "max", "bl": "min"}).dropna()
    h, l, t = m15["bh"].to_numpy(), m15["bl"].to_numpy(), m15.index.to_numpy()
    out = {}
    for name, x, sign in (("hi", h, 1), ("lo", l, -1)):
        y = x * sign
        piv = np.zeros(len(y), bool)
        piv[2:-2] = (y[2:-2] > np.maximum(y[1:-3], y[:-4])) & (y[2:-2] > np.maximum(y[3:-1], y[4:]))
        # next index whose value exceeds this one (first time the swing's stops get run)
        nxt = np.full(len(y), len(y) - 1)
        stack = []
        for i in range(len(y)):
            while stack and y[i] > y[stack[-1]]:
                nxt[stack.pop()] = i
            stack.append(i)
        idx = np.where(piv)[0]
        taken = t[nxt[idx]]
        taken[nxt[idx] == len(y) - 1] = np.datetime64("2100-01-01")
        out[name] = (t[idx] + np.timedelta64(30, "m"), x[idx], taken)   # known 2 bars later
    return out


def untouched(fr, at, lo_px, hi_px):
    """Count swings known before `at`, from the last 7 days, not yet traded through, inside the band."""
    known, px, taken = fr
    m = (known < at) & (known >= at - np.timedelta64(7, "D")) & (taken >= at) & (px > lo_px) & (px <= hi_px)
    return int(m.sum())


def simulate(m1, i0, side, entry, stop, tp, be, flat_min, limit=None, valid_until=None):
    """Return R multiple (None if a limit order never fills). Stop beats target in the same minute."""
    risk = (entry - stop) * side
    n = len(m1["bo"])
    i = i0
    if limit is not None:                         # wait for the pullback into the order block
        filled = False
        while i < n and m1["lmin"][i] < valid_until:
            if side < 0:
                if m1["ah"][i] >= stop or m1["al"][i] <= tp:     # invalidated / ran away first
                    if not m1["bh"][i] >= entry:
                        return None
                if m1["bh"][i] >= entry:
                    filled = True
                    if m1["ah"][i] >= stop:
                        return -1.0
                    break
            else:
                if m1["bl"][i] <= stop or m1["bh"][i] >= tp:
                    if not m1["al"][i] <= entry:
                        return None
                if m1["al"][i] <= entry:
                    filled = True
                    if m1["bl"][i] <= stop:
                        return -1.0
                    break
            i += 1
        if not filled:
            return None
        i += 1
    moved = False
    for j in range(i, n):
        if m1["lmin"][j] >= flat_min:
            px = m1["bo"][j] if side > 0 else m1["ao"][j]
            return (px - entry) * side / risk
        if side < 0:
            if m1["ah"][j] >= stop:
                return (entry - max(stop, m1["ao"][j])) / risk
            if m1["al"][j] <= tp:
                return (entry - tp) / risk
            if be and not moved and m1["al"][j] <= entry - risk:
                stop, moved = entry, True
        else:
            if m1["bl"][j] <= stop:
                return (min(stop, m1["bo"][j]) - entry) / risk
            if m1["bh"][j] >= tp:
                return (tp - entry) / risk
            if be and not moved and m1["bh"][j] >= entry + risk:
                stop, moved = entry, True
    px = m1["bc"][n - 1] if side > 0 else m1["ac"][n - 1]
    return (px - entry) * side / risk


def find_setup(m5, hi, lo):
    """First sweep followed by a structure shift. Returns indices and levels, or None."""
    o, h, l, c = (m5[x].to_numpy() for x in ("bo", "bh", "bl", "bc"))
    st = {-1: None, 1: None}                       # side -> [extreme, extreme index, first sweep index]
    for i in range(len(c)):
        if h[i] > hi:
            s = st[-1]
            st[-1] = [h[i], i, i] if s is None else ([h[i], i, s[2]] if h[i] > s[0] else s)
        if l[i] < lo:
            s = st[1]
            st[1] = [l[i], i, i] if s is None else ([l[i], i, s[2]] if l[i] < s[0] else s)
        for side in (-1, 1):
            s = st[side]
            if s is None or i <= s[1] or s[1] == 0:
                continue
            ext, xi, first = s
            look = slice(max(0, xi - 6), xi)
            ref = l[look].min() if side < 0 else h[look].max()
            if (side < 0 and c[i] < ref) or (side > 0 and c[i] > ref):
                # order block: last opposite-close candle at/before the extreme (up to 6 back)
                ob = xi
                for k in range(xi, max(-1, xi - 7), -1):
                    if (side < 0 and c[k] > o[k]) or (side > 0 and c[k] < o[k]):
                        ob = k
                        break
                fvg = any((side < 0 and h[k + 1] < l[k - 1]) or (side > 0 and l[k + 1] > h[k - 1])
                          for k in range(max(xi, 1), i))
                return dict(side=side, shift=i, ext=ext, xi=xi, first=first, ob=ob, fvg=fvg)
    return None


def signals(sym):
    df = load(sym)
    if "up" not in df:
        df["up"] = df["dn"] = 0
    ctx = daily_context(df)
    fr = fractals(df)
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
            m5 = win.resample("5min").agg({"bo": "first", "bh": "max", "bl": "min", "bc": "last",
                                           "n": "sum", "up": "sum", "dn": "sum"}).dropna()
            if len(m5) < 8:
                continue
            s = find_setup(m5, hi, lo)
            if s is None:
                continue
            side, xi, sh = s["side"], s["xi"], s["shift"]
            m1 = {c: sess[c].to_numpy() for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "lmin")}
            i0 = sess.index.searchsorted(m5.index[sh] + pd.Timedelta(minutes=5))
            if i0 >= len(sess) or m1["lmin"][i0] >= w1 * 60:
                continue
            spread = m1["ao"][i0] - m1["bo"][i0]
            c = ctx.loc[day]
            o5, h5, l5, c5 = (m5[x].to_numpy() for x in ("bo", "bh", "bl", "bc"))
            ob_hi, ob_lo = h5[s["ob"]], l5[s["ob"]]
            mt = (o5[s["ob"]] + c5[s["ob"]]) / 2                 # mean threshold of the OB body
            if side < 0:
                stop = max(s["ext"], ob_hi) + spread
            else:
                stop = min(s["ext"], ob_lo) - spread
            mkt = m1["bo"][i0] if side < 0 else m1["ao"][i0]
            # order flow on the sweep-extreme and shift candles
            n5, d5 = m5["n"].to_numpy(), (m5["up"] - m5["dn"]).to_numpy()
            base_vol = np.median(n5[max(0, xi - 24):xi]) if xi > 0 else np.nan
            lean = lambda k: d5[k] / n5[k] if n5[k] > 0 else 0.0
            # heat map: stacked untouched swings the sweep cleared, and liquidity toward the target
            at = np.datetime64(sess.index[0])
            level = hi if side < 0 else lo
            band = 0.1 * c["atr"]
            if side < 0:
                heat = untouched(fr["hi"], at, level - band, s["ext"])
            else:
                heat = untouched((fr["lo"][0], -fr["lo"][1], fr["lo"][2]), at, -level - band, -s["ext"])
            base = dict(sym=sym, model=model, day=day, side=side, atr=c["atr"], fvg=s["fvg"],
                        quick=s["shift"] - s["first"] <= 6,
                        trend=bool(c["t20"] == side and c["t50"] == side),
                        of_spike=bool(base_vol > 0 and n5[xi] >= 1.5 * base_vol),
                        of_absorb=bool(lean(xi) * -side >= 0.10),
                        of_disp=bool(lean(sh) * side >= 0.10),
                        heat=heat >= 2, heat_n=heat)
            for entry_kind in ("ob", "mkt"):
                entry = mt if entry_kind == "ob" else mkt
                risk = (entry - stop) * side
                if risk <= 0 or risk < 3 * spread:
                    continue
                if entry_kind == "ob" and (mkt - entry) * side <= 0:   # OB must be a pullback away
                    continue
                t3 = entry + side * 3 * risk
                if side < 0:
                    magnet = untouched((fr["lo"][0], -fr["lo"][1], fr["lo"][2]), at, -entry, -t3)
                else:
                    magnet = untouched(fr["hi"], at, entry, t3)
                row = dict(base, entry_kind=entry_kind, time=sess.index[i0], entry=entry, stop=stop,
                           risk=risk, spread_r=spread / risk, magnet=magnet >= 1,
                           sane=0.05 * c["atr"] <= risk <= 0.4 * c["atr"])
                lim = dict(limit=True, valid_until=w1 * 60) if entry_kind == "ob" else {}
                for tg in TARGETS:
                    if tg == "range":
                        tp = lo if side < 0 else hi
                        if (tp - entry) * side < risk:
                            row["r_range"] = np.nan
                            continue
                    else:
                        tp = entry + side * float(tg[0]) * risk
                    row[f"r_{tg}"] = simulate(m1, i0, side, entry, stop, tp, tg.endswith("be"), flat * 60, **lim)
                if entry_kind == "ob" and all(row.get(f"r_{tg}") is None for tg in TARGETS):
                    continue                                       # limit never filled
                rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    from concurrent.futures import ProcessPoolExecutor
    syms = sys.argv[1:] or ["XAUUSDm", "EURUSDm", "GBPUSDm", "USDJPYm"]
    with ProcessPoolExecutor(len(syms)) as ex:
        out = pd.concat(ex.map(signals, syms))
    out.to_parquet(OUT / "ict_signals.parquet")
    print(out.groupby(["sym", "model", "entry_kind"]).size())
