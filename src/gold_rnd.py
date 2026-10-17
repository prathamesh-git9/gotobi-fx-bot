"""Gold-only R&D: more entry filters and win-rate-oriented exit management.

Entries (both on 5-min bid candles after a sweep of the Asian or previous-day high/low):
  reclaim  first candle that closes back inside the swept level
  mss      first candle that closes beyond the pre-sweep structure (market-structure shift)

Exit plans, all simulated on 1-minute bid/ask bars (stop beats target inside one minute):
  T1 T1.5 T2 T3 T4          fixed target, full position
  BE2 BE3 BE4               stop to break-even once +1R, then target 2/3/4R
  P2 P3 P4                  bank half at +1R, stop to break-even, runner to 2/3/4R
  PT                        bank half at +1R, runner trails 1R behind the best price until the flat time
  TR                        no partial; after +1R the stop trails 1R behind the best price

Costs: the account's real spread is in the fills. `comm` (price units per oz, round trip) and
`slip` (price units per oz, round trip) are charged on every trade, in R.
"""
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import load
from confluence import daily_context, first_reclaim
from ict import find_setup

RES = Path(__file__).resolve().parent.parent / "results"
WINDOWS = {"asia": (7, 10, 16), "pdhl": (7, 16, 20)}
PLANS = ["T1", "T1.5", "T2", "T3", "T4", "BE2", "BE3", "BE4", "P2", "P3", "P4", "PT", "TR"]


def plan_r(m1, i0, side, entry, risk, plan, flat_min):
    """Gross R for one exit plan (before commission/slippage)."""
    stop = entry - side * risk
    partial = plan.startswith("P")
    trail = plan in ("PT", "TR")
    be = plan.startswith(("BE", "P")) or trail
    k = None if trail else float(plan.lstrip("TBEP"))
    tp = entry + side * k * risk if k else None
    banked, size, armed, best = 0.0, 1.0, False, entry
    n = len(m1["bo"])
    for i in range(i0, n):
        if m1["lmin"][i] >= flat_min:
            px = m1["bo"][i] if side > 0 else m1["ao"][i]
            return banked + size * (px - entry) * side / risk
        hi_x = m1["bh"][i] if side > 0 else m1["ah"][i]        # price the position exits at
        lo_x = m1["bl"][i] if side > 0 else m1["al"][i]
        adverse, favour = (lo_x, hi_x) if side > 0 else (hi_x, lo_x)
        op = m1["bo"][i] if side > 0 else m1["ao"][i]
        if (adverse - stop) * side <= 0:                       # stopped (gap fills at the open)
            px = min(stop, op) if side > 0 else max(stop, op)
            return banked + size * (px - entry) * side / risk
        if tp is not None and (favour - tp) * side >= 0:
            return banked + size * k
        if not armed and (favour - (entry + side * risk)) * side >= 0:
            armed = True
            if partial:
                banked, size = 0.5, 0.5
            if be:
                stop = entry
        if trail and armed:
            best = favour if (favour - best) * side > 0 else best
            stop = max(stop, best - risk) if side > 0 else min(stop, best + risk)
    px = m1["bc"][n - 1] if side > 0 else m1["ac"][n - 1]
    return banked + size * (px - entry) * side / risk


def signals(sym="XAUUSDm", comm=0.0, slip=0.0):
    df = load(sym)
    ctx = daily_context(df)
    g = df.groupby("lday")
    day = pd.DataFrame({"o": g["bo"].first(), "h": g["bh"].max(), "l": g["bl"].min(), "c": g["bc"].last(),
                        "n": g.size()})
    day = day[day["n"] > 600]
    asia = df[df["lhour"] < 7].groupby("lday").agg(ah=("bh", "max"), al=("bl", "min"), an=("bh", "size"))
    prev = pd.DataFrame({"pdh": day["h"].shift(1), "pdl": day["l"].shift(1),
                         "pd_up": (day["c"] > day["o"]).shift(1),
                         "w_hi": day["h"].rolling(5).max().shift(1), "w_lo": day["l"].rolling(5).min().shift(1)})
    atr_med = ctx["atr"].rolling(100, min_periods=50).median()
    rows = []
    for d, dd in df.groupby("lday", sort=True):
        if d not in prev.index or d not in ctx.index or d not in asia.index or pd.isna(prev.at[d, "w_hi"]):
            continue
        a, p, c = asia.loc[d], prev.loc[d], ctx.loc[d]
        if a["an"] < 300:
            continue
        day_open = dd["bo"].iat[0]
        fri = pd.Timestamp(d).weekday() == 4
        nfp = fri and pd.Timestamp(d).day <= 7                 # first Friday: US payrolls
        for model, (w0, w1, flat) in WINDOWS.items():
            hi, lo = (a["ah"], a["al"]) if model == "asia" else (p["pdh"], p["pdl"])
            sess = dd[(dd["lhour"] >= w0) & (dd["lhour"] < flat)]
            if len(sess) < 60 or not (lo < sess["bo"].iat[0] < hi):
                continue
            win = sess[sess["lhour"] < w1]
            m5 = win[["bo", "bh", "bl", "bc"]].resample("5min").agg(
                {"bo": "first", "bh": "max", "bl": "min", "bc": "last"}).dropna()
            if len(m5) < 8:
                continue
            m1 = {k: sess[k].to_numpy() for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac", "lmin")}
            for entry_kind in ("reclaim", "mss"):
                if entry_kind == "reclaim":
                    s = first_reclaim(m5, hi, lo)
                    if s is None:
                        continue
                    sig_i, ext, side = s["i"], s["ext"], s["side"]
                    extra = dict(quick=s["quick"], strong=s["strong"], mss_too=s["mss"],
                                 shallow=s["depth"] <= 0.25 * c["atr"])
                else:
                    s = find_setup(m5, hi, lo)
                    if s is None:
                        continue
                    sig_i, ext, side = s["shift"], s["ext"], s["side"]
                    depth = (ext - hi) if side < 0 else (lo - ext)
                    extra = dict(quick=s["shift"] - s["first"] <= 6, strong=s["fvg"], mss_too=True,
                                 shallow=depth <= 0.25 * c["atr"])
                i0 = sess.index.searchsorted(m5.index[sig_i] + pd.Timedelta(minutes=5))
                if i0 >= len(sess) or m1["lmin"][i0] >= w1 * 60:
                    continue
                spread = m1["ao"][i0] - m1["bo"][i0]
                entry = m1["bo"][i0] if side < 0 else m1["ao"][i0]
                stop = ext + spread if side < 0 else ext - spread
                risk = (stop - entry) * -side
                if risk <= 0 or risk < 3 * spread:
                    continue
                hour = int(m1["lmin"][i0] // 60)
                other_hi, other_lo = (p["pdh"], p["pdl"]) if model == "asia" else (a["ah"], a["al"])
                mid5 = (p["w_hi"] + p["w_lo"]) / 2
                row = dict(sym=sym, model=model, entry_kind=entry_kind, day=d, time=sess.index[i0], side=side,
                           entry=entry, risk=risk, spread_r=spread / risk, cost_r=(comm + slip) / risk,
                           trend=bool(c["t20"] == side and c["t50"] == side),
                           sane=bool(0.05 * c["atr"] <= risk <= 0.4 * c["atr"]),
                           lon_open=hour < 9, ny=hour >= 12, midweek=pd.Timestamp(d).weekday() in (1, 2, 3),
                           no_nfp=not nfp, vol_hi=bool(c["atr"] > atr_med.get(d, np.nan)),
                           premium=bool((entry > mid5) if side < 0 else (entry < mid5)),
                           above_open=bool((entry > day_open) if side < 0 else (entry < day_open)),
                           stacked=bool((ext > other_hi) if side < 0 else (ext < other_lo)),
                           asia_tight=bool((a["ah"] - a["al"]) < 0.4 * c["atr"]),
                           pd_against=bool(p["pd_up"] == (side < 0)), **extra)
                for pl in PLANS:
                    row[pl] = plan_r(m1, i0, side, entry, risk, pl, flat * 60) - row["cost_r"]
                rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSDm"
    comm = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    slip = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    out = signals(sym, comm, slip)
    out.to_parquet(RES / f"gold_rnd_{sym}.parquet")
    print(out.groupby(["model", "entry_kind"]).size())
    print(out[PLANS].agg(["mean", lambda x: (x > 0).mean()]).round(3))
