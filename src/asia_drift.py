"""Gold Asian-session drift: buy after the New York rollover, sell into the London open.

Entry: first minute at/after 18:00 New York time (Sun-Thu evenings) at the real ask.
Exit:  take-profit / stop on 1-minute bars, otherwise the first minute at/after 03:00 New York at the bid.
The position never crosses the 17:00 NY rollover, so it pays no swap.

Exit parameters are fractions of yesterday's daily ATR(14):
  tp  in {0.10, 0.15, 0.20, 0.30, none}
  sl  in {0.30, 0.50, 1.00}           (also the position-sizing distance, so 1R = sl x ATR)
Filters (yes/no, known at entry): trend50/100/200 (close above SMA), ny_down (the 08-17 NY session
fell), vol_hi (ATR above its 100-day median), not_fri (skip Thursday-evening entries into NFP/Friday).
"""
from itertools import combinations, product

import numpy as np
import pandas as pd

from eval_high_wr import CGT, CUT, END, EURUSD, EXEMPT_EUR, MID, S0, S1, SEL0, account
from high_wr import RES, SLIP, daily_bars, load_gold

TPS = [0.10, 0.15, 0.20, 0.30, None]
SLS = [0.30, 0.50, 1.00]
F = ["trend50", "trend100", "trend200", "ny_down", "vol_hi", "not_fri"]


def build(df, d):
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    mins = ny.hour * 60 + ny.minute
    nyd = ny.date
    bo, bh, bl, bc = (df[c].to_numpy() for c in ("bo", "bh", "bl", "bc"))
    ao = df["ao"].to_numpy()
    days = np.array(d.index)
    atr_med = d["atr"].rolling(100, min_periods=50).median()
    # candidate entries: first minute >= 18:00 NY each calendar evening
    is_entry = (mins >= 18 * 60) & np.r_[True, (mins[1:] >= 18 * 60) & ((mins[:-1] < 18 * 60) | (nyd[1:] != nyd[:-1]))]
    ent_idx = np.flatnonzero(is_entry)
    is_exit = (mins >= 3 * 60) & (mins < 17 * 60)
    exit_first = np.flatnonzero(is_exit & np.r_[True, ~is_exit[:-1]])
    ny_open = np.flatnonzero((mins >= 8 * 60) & np.r_[True, mins[:-1] < 8 * 60])
    rows = []
    for e in ent_idx:
        wd = ny[e].weekday()                       # 6=Sun ... 3=Thu evening
        if wd in (4, 5):
            continue
        k = np.searchsorted(exit_first, e)
        if k >= len(exit_first):
            break
        x = exit_first[k]
        if (df.index[x] - df.index[e]) > pd.Timedelta(hours=12):
            continue                               # data gap / holiday
        # yesterday's completed daily bar (keyed at 16:00 NY): the last key strictly before entry
        key = (ny[e] + pd.Timedelta(hours=8)).date()
        j = np.searchsorted(days, key) - 1
        if j < 200 or np.isnan(d["atr"].iat[j]):
            continue
        atr, close = d["atr"].iat[j], d["c"].iat[j]
        o8 = ny_open[np.searchsorted(ny_open, e) - 1]
        ny_ret = bc[e - 1] - bo[o8] if df.index[e] - df.index[o8] < pd.Timedelta(hours=11) else 0.0
        entry = ao[e]
        row = dict(day=key, wd=wd, entry=entry, atr=atr, spread=ao[e] - bo[e],
                   trend50=close > d["sma50"].iat[j], trend100=close > d["sma100"].iat[j],
                   trend200=close > d["sma200"].iat[j], ny_down=ny_ret < 0,
                   vol_hi=atr > atr_med.iat[j], not_fri=wd != 3,
                   ret=(bo[x] - entry) / entry)
        seg_h, seg_l, seg_o = bh[e:x + 1], bl[e:x + 1], bo[e:x + 1]
        for tp, sl in product(TPS, SLS):
            stop = entry - sl * atr
            tgt = entry + tp * atr if tp else np.inf
            hit_s = np.flatnonzero(seg_l <= stop)
            hit_t = np.flatnonzero(seg_h >= tgt)
            fs = hit_s[0] if len(hit_s) else 10**9
            ft = hit_t[0] if len(hit_t) else 10**9
            if fs <= ft and fs < 10**9:            # stop first (or same minute)
                px = min(stop, seg_o[fs])
            elif ft < 10**9:
                px = tgt
            else:
                px = bo[x]
            row[f"r_{tp}_{sl}"] = (px - entry - SLIP) / (sl * atr)
        rows.append(row)
    return pd.DataFrame(rows)


def part(t, a, b):
    return t[(t.day >= a) & (t.day <= b)]


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    df = load_gold()
    d = daily_bars(df)
    t = build(df, d)
    t.to_parquet(RES / "asia_drift.parquet")
    print("nights", len(t), t.day.min(), "->", t.day.max(), " median entry spread $", round(t.spread.median(), 3))
    print("\nBuy 18:00 / sell 03:00 NY, no stop/target, gross return per night:")
    for label, a, b in (("2015-18", S0, S1), ("2019-Sep23", SEL0, CUT), ("last 3y", CUT, END)):
        x = part(t, a, b)
        print(f"  {label:10s} nights {len(x)}  win {np.mean(x.ret > 0):.0%}  avg {x.ret.mean():+.4%}  "
              f"after $0.10 slip+spread win {np.mean(x['r_None_1.0'] > 0):.0%}")
    rcols = [c for c in t.columns if c.startswith("r_")]
    sel = part(t, SEL0, CUT - pd.Timedelta(days=1))
    first = (sel.day < MID).to_numpy()
    rows = []
    for k in range(3):
        for combo in combinations(F, k):
            m = np.ones(len(sel), bool)
            for f in combo:
                m &= sel[f].to_numpy(bool)
            if m.sum() < 150:
                continue
            for rc in rcols:
                r = sel[rc].to_numpy()
                rows.append(dict(filters="+".join(combo) or "-", plan=rc, n=m.sum(), win=(r[m] > 0).mean(),
                                 avg=r[m].mean(), t=r[m].mean() / (r[m].std(ddof=1) / np.sqrt(m.sum())),
                                 h1=r[m & first].mean(), h2=r[m & ~first].mean()))
    g = pd.DataFrame(rows)
    ok = g[(g.win >= 0.60) & (g.h1 > 0) & (g.h2 > 0)].sort_values("t", ascending=False)
    print(f"\nrules {len(g)}; >=60% win AND profitable in both halves of 2019-23: {len(ok)}")

    def apply(df_, row):
        x = df_
        for f in ([] if row.filters == "-" else row.filters.split("+")):
            x = x[x[f]]
        return x

    out = []
    for _, row in ok.head(20).iterrows():
        rec = dict(filters=row.filters, plan=row.plan, n_sel=row.n, win_sel=row.win, avg_sel=row.avg, t_sel=row.t)
        for label, a, b in (("3y", CUT, END), ("1518", S0, S1)):
            x = apply(part(t, a, b), row)[row.plan]
            rec.update({f"n_{label}": len(x), f"win_{label}": (x > 0).mean(), f"avg_{label}": x.mean()})
        out.append(rec)
    out = pd.DataFrame(out)
    print(out.round(3).to_string(index=False))
    print(f"Top-20 average: 2019-23 win {out.win_sel.mean():.0%} avg {out.avg_sel.mean():+.3f}R | last 3y win "
          f"{out.win_3y.mean():.0%} avg {out.avg_3y.mean():+.3f}R | 2015-18 win {out.win_1518.mean():.0%} avg {out.avg_1518.mean():+.3f}R")
    best = ok.iloc[0]
    print("\nWINNER (chosen on 2019 - Sep 2023 only):", best.filters, best.plan)
    for label, a, b in (("2019-Sep 2023 (selection)", SEL0, CUT - pd.Timedelta(days=1)),
                        ("Oct 2023-Sep 2026 (last 3 years)", CUT, END), ("2015-2018 (stress)", S0, S1)):
        x = apply(part(t, a, b), best).copy()
        x["day"] = pd.to_datetime(x["day"])
        r = x[best.plan]
        bal, dd, tax = account(x.assign(r=r), "r")
        print(f"  {label}: {len(x)} trades, win {np.mean(r > 0):.0%}, avg {r.mean():+.3f}R, "
              f"$1,000 -> ${bal:,.0f} after costs+tax (tax ${tax:,.0f}), max DD {dd:.0%}")
