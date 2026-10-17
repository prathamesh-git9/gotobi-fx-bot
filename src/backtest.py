"""Liquidity-sweep reversal backtester on 1-minute bid/ask bars.

Setup (both models share the same machinery, only the liquidity levels differ):
  1. Mark a liquidity pool: a level where resting stops cluster.
       asia : the Asian-session high/low (00:00-07:00 London time)
       pdhl : the previous London day's high/low
  2. Sweep: inside the trade window, bid trades beyond the level.
  3. Price-action confirmation on 5-minute bid candles, either
       reclaim : a candle closes back inside the level (failed breakout)
       mss     : after the sweep, a candle closes beyond the low (high) of the
                 6 candles before the sweep extreme -- a market-structure shift
  4. Enter at the next minute's open, stop just beyond the sweep extreme,
     target either a fixed R multiple or the opposite side of the pool.

Fills are honest about the spread: shorts sell the bid and buy back the ask,
longs buy the ask and sell the bid. Stops gap through at the bar open when the
bar opens beyond them. If a 1-minute bar touches both stop and target, the stop
wins. Everything is flat by the session cut-off, so there is no swap.
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
TZ = "Europe/London"


@dataclass(frozen=True)
class Params:
    model: str = "asia"        # asia | pdhl
    confirm: str = "reclaim"   # reclaim | mss
    target: str = "2R"         # "1R" "2R" "3R" or "range"
    win_start: int = 7         # London hour the sweep/entry window opens
    win_end: int = 10          # London hour it closes (no new entries after)
    flat: int = 16             # London hour everything is closed
    mss_lookback: int = 6      # 5-minute candles that define the structure level
    min_risk_spreads: float = 3.0  # skip trades whose stop is under N spreads away
    bias: str = "none"         # none | with | against: daily trend (prior close vs 20-day SMA)


def load(sym):
    df = pd.read_parquet(DATA / f"{sym}_m1.parquet")
    df.columns = [c[0] + c[1] if c[1:] in ("open", "high", "low", "close") else c for c in df.columns]
    local = df.index.tz_localize("UTC").tz_convert(TZ)
    df["lday"] = local.date
    df["lhour"] = local.hour
    df["lmin"] = local.hour * 60 + local.minute
    return df


def day_levels(df, model):
    """Liquidity levels per London day, keyed by date."""
    if model == "asia":
        a = df[df["lhour"] < 7]
        g = a.groupby("lday")
        return pd.DataFrame({"hi": g["bh"].max(), "lo": g["bl"].min(), "nbars": g.size()})
    g = df.groupby("lday")
    daily = pd.DataFrame({"hi": g["bh"].max(), "lo": g["bl"].min(), "nbars": g.size()})
    daily = daily[daily["nbars"] > 600]          # skip half-days / holiday stubs
    return daily.shift(1).dropna()


def daily_trend(df):
    """+1 if yesterday's close was above its 20-day SMA, else -1 (known before today opens)."""
    close = df.groupby("lday")["bc"].last()
    close = close[df.groupby("lday").size() > 600]
    return np.sign(close - close.rolling(20).mean()).shift(1).dropna()


def simulate_exit(m1, i0, side, stop, tp, flat_min):
    """Walk 1-minute bars from index i0; return (exit_price, exit_index, reason)."""
    bo, bh, bl, bc = m1["bo"], m1["bh"], m1["bl"], m1["bc"]
    ao, ah, al, ac = m1["ao"], m1["ah"], m1["al"], m1["ac"]
    lmin = m1["lmin"]
    n = len(bo)
    for i in range(i0, n):
        if lmin[i] >= flat_min:
            return (bo[i] if side > 0 else ao[i]), i, "time"
        if side < 0:                       # short: exits on the ask
            if ah[i] >= stop:
                return max(stop, ao[i]), i, "sl"
            if al[i] <= tp:
                return tp, i, "tp"
        else:                              # long: exits on the bid
            if bl[i] <= stop:
                return min(stop, bo[i]), i, "sl"
            if bh[i] >= tp:
                return tp, i, "tp"
    last = n - 1
    return (bc[last] if side > 0 else ac[last]), last, "eod"


def run(sym, p: Params, df=None):
    df = load(sym) if df is None else df
    levels = day_levels(df, p.model)
    trend = daily_trend(df)
    trades = []
    for day, d in df.groupby("lday", sort=True):
        if day not in levels.index:
            continue
        hi, lo = levels.at[day, "hi"], levels.at[day, "lo"]
        if p.model == "asia" and levels.at[day, "nbars"] < 300:
            continue
        sess = d[(d["lhour"] >= p.win_start) & (d["lhour"] < p.flat)]
        if len(sess) < 60:
            continue
        # a sweep needs price to start the window inside the pool
        first = sess.iloc[0]
        if not (lo < first["bo"] < hi):
            continue
        m1 = {c: sess[c].to_numpy() for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "lmin")}
        m1_times = sess.index
        win = sess[sess["lhour"] < p.win_end]
        m5 = win[["bo", "bh", "bl", "bc"]].resample("5min", label="left", closed="left").agg(
            {"bo": "first", "bh": "max", "bl": "min", "bc": "last"}).dropna()
        if len(m5) < 3:
            continue
        sig = find_signal(m5, hi, lo, p)
        if sig is None:
            continue
        side, sig_time, extreme = sig
        if p.bias != "none":
            if day not in trend.index:
                continue
            agrees = side == trend.at[day]
            if agrees != (p.bias == "with"):
                continue
        entry_t = sig_time + pd.Timedelta(minutes=5)
        i0 = m1_times.searchsorted(entry_t)
        if i0 >= len(m1_times) or m1["lmin"][i0] >= p.win_end * 60:
            continue
        spread = m1["ao"][i0] - m1["bo"][i0]
        if side < 0:
            entry = m1["bo"][i0]
            stop = extreme + spread           # ask must clear the swept high
            risk = stop - entry
        else:
            entry = m1["ao"][i0]
            stop = extreme - spread
            risk = entry - stop
        if risk <= 0 or risk < p.min_risk_spreads * spread:
            continue
        if p.target == "range":
            tp = lo if side < 0 else hi
            if (entry - tp) * -side <= 0 or abs(entry - tp) < risk * 0.5:
                continue
        else:
            k = float(p.target.rstrip("R"))
            tp = entry + side * k * risk
        px, ix, why = simulate_exit(m1, i0, side, stop, tp, p.flat * 60)
        r = (px - entry) * side / risk
        tdir = trend.get(day, 0.0)
        trades.append(dict(day=day, time=m1_times[i0], side=side, with_trend=int(side == tdir),
                           has_trend=int(tdir != 0), entry=entry, stop=stop, tp=tp,
                           exit=px, exit_time=m1_times[ix], reason=why, risk=risk,
                           spread_r=spread / risk, r=r))
    return pd.DataFrame(trades)


def find_signal(m5, hi, lo, p):
    """Return (side, signal_bar_time, sweep_extreme) for the first confirmed sweep."""
    h, l, c = m5["bh"].to_numpy(), m5["bl"].to_numpy(), m5["bc"].to_numpy()
    t = m5.index
    up_ext = dn_ext = None          # running sweep extremes
    up_i = dn_i = None              # bar index of the extreme
    for i in range(len(c)):
        if h[i] > hi and (up_ext is None or h[i] > up_ext):
            up_ext, up_i = h[i], i
        if l[i] < lo and (dn_ext is None or l[i] < dn_ext):
            dn_ext, dn_i = l[i], i
        if up_ext is not None:
            if p.confirm == "reclaim" and c[i] < hi:
                return -1, t[i], up_ext
            if p.confirm == "mss" and i > up_i:
                ref = l[max(0, up_i - p.mss_lookback):up_i].min() if up_i > 0 else l[0]
                if c[i] < ref:
                    return -1, t[i], up_ext
        if dn_ext is not None:
            if p.confirm == "reclaim" and c[i] > lo:
                return 1, t[i], dn_ext
            if p.confirm == "mss" and i > dn_i:
                ref = h[max(0, dn_i - p.mss_lookback):dn_i].max() if dn_i > 0 else h[0]
                if c[i] > ref:
                    return 1, t[i], dn_ext
    return None


def stats(tr):
    if tr is None or len(tr) == 0:
        return dict(n=0)
    r = tr["r"].to_numpy()
    eq = np.cumsum(r)
    dd = (np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    years = max((tr["day"].iloc[-1] - tr["day"].iloc[0]).days / 365.25, 1e-9)
    return dict(n=len(r), win=round((r > 0).mean() * 100, 1), avgR=round(r.mean(), 3),
                PF=round(wins / losses, 2) if losses else np.inf, totR=round(r.sum(), 1),
                maxDD_R=round(dd, 1), R_per_yr=round(r.sum() / years, 1),
                t=round(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))), 2) if len(r) > 2 else np.nan,
                spread_R=round(tr["spread_r"].mean(), 3),
                grossR=round((r + tr["spread_r"].to_numpy()).mean(), 3))
