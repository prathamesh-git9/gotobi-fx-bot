"""Gold Asia Night v2: can the rule be improved without fooling ourselves?

Per NY evening (Sun-Thu) and per plan:
  entry  E in {18:05, 18:30, 19:00, 20:00} NY   (18:00 itself has the widest-spread tail)
  exit   X in {01:00, 02:00, 03:00, 04:00, 05:00} NY next morning, unless TP/SL hit first
  tp     in {0.10, 0.15, 0.20, 0.30, none} x yesterday's daily ATR(14)
  sl     in {0.30, 0.50, 1.00} x ATR          (1R = sl x ATR)
Filters known at entry: ny_down, big_dip (08-17 NY fell > 0.3 ATR), vol_hi (ATR > 100-day median),
trend50, trend200, not_fri, below_sma5. Up to 3 at once -> 64 filter sets x 300 plans = 19,200 rules.

Costs: actual = buy the real ask, stop/target/exit on the real bid, + $0.10/oz slippage.
       modern = mid prices, minus today's spread (0.007% of price) + $0.10/oz.
Walk-forward: each year from 2018, choose the rule on all earlier nights only (modern costs, >= 60% win,
>= 100 trades, profitable in both halves of the training data, best t-stat), then trade the next year blind.
"""
from itertools import combinations, product

import numpy as np
import pandas as pd

from eval_high_wr import CUT, END, settle
from high_wr import RES, SLIP, daily_bars, load_gold

ENTRIES = [18 * 60 + 5, 18 * 60 + 30, 19 * 60, 20 * 60]
EXITS = [60, 120, 180, 240, 300]
TPS = [0.10, 0.15, 0.20, 0.30, None]
SLS = [0.30, 0.50, 1.00]
F = ["ny_down", "big_dip", "vol_hi", "trend50", "trend200", "not_fri", "below_sma5"]
MODERN = 0.00007
PLANS = list(product(ENTRIES, EXITS, TPS, SLS))


def first_hit_le(cummin, lv):
    """index of the first bar whose running low <= lv (len if never)."""
    return np.searchsorted(-cummin, -np.asarray(lv), side="left")


def first_hit_ge(cummax, lv):
    return np.searchsorted(cummax, np.asarray(lv), side="left")


def outcomes(lo, hi, op, exit_px, n_x, entry, atr, cost):
    """r for every (X, tp, sl) given one entry. lo/hi/op: bar arrays from entry to the latest exit."""
    cmin, cmax = np.minimum.accumulate(lo), np.maximum.accumulate(hi)
    out = {}
    for sl in SLS:
        stop = entry - sl * atr
        fs = int(first_hit_le(cmin, stop))
        for tp in TPS:
            ft = int(first_hit_ge(cmax, entry + tp * atr)) if tp else 10**9
            for X, nx, xp in zip(EXITS, n_x, exit_px):
                if fs < nx and fs <= ft:
                    px = min(stop, op[fs])
                elif ft < nx:
                    px = entry + tp * atr
                else:
                    px = xp
                out[(X, tp, sl)] = (px - entry - cost) / (sl * atr)
    return out


def build(df, d):
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York")
    nyl = ny.tz_localize(None).values
    mins = (ny.hour * 60 + ny.minute).to_numpy()
    bo, bh, bl, bc, ao = (df[c].to_numpy() for c in ("bo", "bh", "bl", "bc", "ao"))
    mo, mh, ml = (df.bo + df.ao).to_numpy() / 2, (df.bh + df.ah).to_numpy() / 2, (df.bl + df.al).to_numpy() / 2
    days = np.array(d.index)
    atr_med = d["atr"].rolling(100, min_periods=50).median().to_numpy()
    dates = pd.to_datetime(pd.Series(ny.date).unique())
    rows = []
    for D in dates:
        wd = D.weekday()
        if wd in (4, 5):
            continue
        a = np.searchsorted(nyl, np.datetime64(D + pd.Timedelta(hours=18)))
        if a >= len(df) or (nyl[a] - np.datetime64(D + pd.Timedelta(hours=18))) > np.timedelta64(30, "m"):
            continue
        key = (D + pd.Timedelta(days=1)).date()
        j = np.searchsorted(days, key) - 1
        if j < 200 or np.isnan(d["atr"].iat[j]) or np.isnan(atr_med[j]):
            continue
        atr, close = d["atr"].iat[j], d["c"].iat[j]
        o8 = np.searchsorted(nyl, np.datetime64(D + pd.Timedelta(hours=8)))
        ny_ret = bc[a - 1] - bo[o8] if (nyl[a] - nyl[o8]) < np.timedelta64(11, "h") and o8 < a else 0.0
        xt = [np.datetime64(D + pd.Timedelta(days=1, minutes=X)) for X in EXITS]
        xi = np.searchsorted(nyl, xt)
        if xi[-1] >= len(df) or (nyl[xi[-1]] - xt[-1]) > np.timedelta64(30, "m"):
            continue
        row = dict(day=key, wd=wd, atr=atr, ny_ret=ny_ret / atr,
                   ny_down=ny_ret < 0, big_dip=ny_ret < -0.3 * atr, vol_hi=atr > atr_med[j],
                   trend50=close > d["sma50"].iat[j], trend200=close > d["sma200"].iat[j],
                   not_fri=wd != 3, below_sma5=close < d["sma5"].iat[j])
        for E in ENTRIES:
            et = np.datetime64(D + pd.Timedelta(minutes=E))
            e = np.searchsorted(nyl, et)
            if (nyl[e] - et) > np.timedelta64(30, "m"):
                continue
            n_x = xi - e
            if E == ENTRIES[0]:
                row.update(entry=ao[e], spread=ao[e] - bo[e])
            # actual: ask in, bid path, bid out
            for (X, tp, sl), r in outcomes(bl[e:xi[-1]], bh[e:xi[-1]], bo[e:xi[-1]], bo[xi], n_x,
                                           ao[e], atr, SLIP).items():
                row[f"a_{E}_{X}_{tp}_{sl}"] = r
            # modern: mid path, today's spread
            for (X, tp, sl), r in outcomes(ml[e:xi[-1]], mh[e:xi[-1]], mo[e:xi[-1]], mo[xi], n_x,
                                           mo[e], atr, MODERN * mo[e] + SLIP).items():
                row[f"m_{E}_{X}_{tp}_{sl}"] = r
        rows.append(row)
    t = pd.DataFrame(rows)
    t["day"] = pd.to_datetime(t["day"])
    return t


def masks(t):
    out = {}
    for k in range(4):
        for combo in combinations(F, k):
            m = np.ones(len(t), bool)
            for f in combo:
                m &= t[f].to_numpy(bool)
            out["+".join(combo) or "-"] = m
    return out


def plan_cols(prefix):
    return [f"{prefix}_{E}_{X}_{tp}_{sl}" for E, X, tp, sl in PLANS]


def choose(t, M, R, train, min_n=100, min_win=0.60):
    """best (filter, plan) on the rows in `train` (bool array)."""
    idx = np.flatnonzero(train)
    half = idx[: len(idx) // 2], idx[len(idx) // 2:]
    best, best_t = None, -np.inf
    Rt = np.nan_to_num(R)
    V = ~np.isnan(R)
    for name, m in M.items():
        mm = m & train
        n = (V & mm[:, None]).sum(0)
        s = (Rt * mm[:, None]).sum(0)
        s2 = (Rt ** 2 * mm[:, None]).sum(0)
        w = ((Rt > 0) & mm[:, None]).sum(0)
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = s / n
            sd = np.sqrt((s2 - n * mean ** 2) / (n - 1))
            tt = mean / (sd / np.sqrt(n))
            win = w / n
        h = [(Rt[hx] * m[hx][:, None]).sum(0) for hx in half]
        ok = (n >= min_n) & (win >= min_win) & (h[0] > 0) & (h[1] > 0)
        if ok.any():
            k = np.nanargmax(np.where(ok, tt, -np.inf))
            if tt[k] > best_t:
                best_t, best = tt[k], (name, k, n[k], win[k], mean[k])
    return best, best_t


def euro_account(day, r, risk, start=100.0, eurusd=1.12):
    bal, peak, dd, year, ypnl, carry, path = start, start, 0.0, None, 0.0, 0.0, []
    for dy, x in zip(day, r):
        if np.isnan(x):
            continue
        if year is not None and dy.year != year:
            bal, carry, _ = settle(bal, ypnl, carry)
            ypnl = 0.0
        year = dy.year
        pnl = bal * risk * x
        bal += pnl
        ypnl += pnl
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
        path.append(bal)
    bal, carry, _ = settle(bal, ypnl, carry)
    return bal, dd, path


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    import os
    cache = RES / "asia_v2_nights.parquet"
    if cache.exists() and not os.environ.get("REBUILD"):
        t = pd.read_parquet(cache)
    else:
        df = load_gold()
        t = build(df, daily_bars(df))
        t.to_parquet(cache)
    print(f"nights {len(t)}  {t.day.min().date()} -> {t.day.max().date()}")
    M = masks(t)
    RM, RA = t[plan_cols("m")].to_numpy(), t[plan_cols("a")].to_numpy()
    years = t.day.dt.year.to_numpy()

    # the v1 rule (18:00 entry is not in the grid; 18:05 is its closest twin)
    v1 = M["ny_down+vol_hi"]
    j1 = PLANS.index((ENTRIES[0], 180, 0.15, 0.30))
    print("\nv1 rule (ny_down+vol_hi, 18:05 in, 03:00 out, tp 0.15, sl 0.3) by year:")
    for y in range(2016, 2027):
        mm = v1 & (years == y)
        print(f"  {y}: n {mm.sum():3d}  modern {np.nanmean(RM[mm, j1]):+.3f}R  actual {np.nanmean(RA[mm, j1]):+.3f}R "
              f" win {np.mean(RM[mm, j1] > 0):.0%}")

    # walk-forward
    print("\nWalk-forward (rule re-chosen every January on all earlier nights, modern costs):")
    wf = []
    for y in range(2018, 2027):
        train, test = years < y, years == y
        best, bt = choose(t, M, RM, train)
        if best is None:
            print(f"  {y}: no rule qualified")
            continue
        name, k, n, win, mean = best
        mm = M[name] & test
        rm, ra = RM[mm, k], RA[mm, k]
        E, X, tp, sl = PLANS[k]
        print(f"  {y}: chose [{name}] in {E // 60}:{E % 60:02d} out {X // 60:02d}:00 tp {tp} sl {sl} "
              f"(train n {n}, win {win:.0%}, {mean:+.3f}R, t {bt:.1f}) -> test n {mm.sum()}, win {np.mean(rm > 0):.0%}, "
              f"modern {np.nanmean(rm):+.3f}R, actual {np.nanmean(ra):+.3f}R")
        wf.append(pd.DataFrame({"day": t.day[mm].to_numpy(), "rm": rm, "ra": ra, "rule": name,
                                "plan": f"{E}_{X}_{tp}_{sl}"}))
    wf = pd.concat(wf).sort_values("day")
    wf.to_parquet(RES / "asia_v2_walkforward.parquet")
    v1t = pd.DataFrame({"day": t.day[v1].to_numpy(), "rm": RM[v1, j1], "ra": RA[v1, j1]})
    v1t = v1t[v1t.day >= wf.day.min()]
    print("\nOut-of-sample 2018-2026 summary:")
    for label, x in (("walk-forward (honest process)", wf), ("v1 fixed rule (partly in-sample)", v1t)):
        print(f"  {label:34s} n {len(x)}  win {np.mean(x.rm > 0):.0%}  modern {x.rm.mean():+.3f}R  actual {x.ra.mean():+.3f}R")
        for risk in (0.02, 0.05, 0.10):
            for col, lab in (("ra", "actual"), ("rm", "modern")):
                b, dd, _ = euro_account(x.day, x[col].to_numpy(), risk)
                b3, dd3, _ = euro_account(x[x.day >= pd.Timestamp(CUT)].day, x[x.day >= pd.Timestamp(CUT)][col].to_numpy(), risk)
                print(f"     risk {risk:.0%} {lab:6s}: EUR 100 -> {b:7,.0f} over 2018-26 (max DD {dd:.0%}) | "
                      f"last 3y EUR 100 -> {b3:5,.0f} (DD {dd3:.0%})")
