"""Choose a >=60%-win-rate gold pullback rule on Jan 2019 - Sep 2023 only, then test it on
  (a) Oct 2023 - Sep 2026 (the last 3 years), and
  (b) 2015 - 2018 (falling and sideways gold, never used for choosing),
and check that the edge is the signal and not just gold's uptrend (random-entry drift test)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from high_wr import GRID, RES, daily_bars, load_gold, run

CUT, MID, END = pd.Timestamp("2023-10-01").date(), pd.Timestamp("2021-07-01").date(), pd.Timestamp("2026-09-30").date()
S0, S1 = pd.Timestamp("2015-01-01").date(), pd.Timestamp("2018-12-31").date()
SEL0 = pd.Timestamp("2019-01-01").date()
CGT, EXEMPT_EUR, EURUSD = 0.33, 1270.0, 1.12


def part(tr, a, b):
    return tr[(tr.day >= a) & (tr.day <= b)] if len(tr) else tr


def summ(r):
    r = np.asarray(r)
    if len(r) < 3:
        return dict(n=len(r), win=np.nan, avg=np.nan, t=np.nan)
    return dict(n=len(r), win=(r > 0).mean(), avg=r.mean(), t=r.mean() / (r.std(ddof=1) / np.sqrt(len(r))))


def drift_test(df, d, tr, n_sims=2000, seed=0):
    """Random entries in the same period, same direction and holding time. p = share of random sets that
    did at least as well as the strategy (gross % return per trade)."""
    rng = np.random.default_rng(seed)
    first_i = d["first_i"].to_numpy()
    days = np.array(d.index)
    bo, ao = df["bo"].to_numpy(), df["ao"].to_numpy()
    lo, hi = np.searchsorted(days, tr.day.min()), np.searchsorted(days, tr.day.max())
    holds, sides = np.maximum(tr.hold.to_numpy(), 1), tr.side.to_numpy()
    means = np.empty(n_sims)
    for s in range(n_sims):
        st = rng.integers(lo, max(lo + 1, hi - 11), len(tr))
        e = first_i[st + 1]
        x = first_i[np.minimum(st + 1 + holds, len(first_i) - 1)]
        ent = np.where(sides > 0, ao[e], bo[e])
        ext = np.where(sides > 0, bo[x], ao[x])
        means[s] = ((ext - ent) * sides / ent).mean()
    return tr.ret.mean(), means.mean(), (means >= tr.ret.mean()).mean()


def account(tr, col, start=1000.0, risk_pct=0.01):
    """1% risk per trade, fractional sizing (Exness Standard Cent trades 0.01 oz), Irish CGT each year."""
    bal, peak, dd, year, ypnl, carry, taxes = start, start, 0.0, None, 0.0, 0.0, 0.0
    for day, r in tr[["day", col]].itertuples(index=False):
        if year is not None and day.year != year:
            bal, carry, t = settle(bal, ypnl, carry)
            taxes += t
            ypnl = 0.0
        year = day.year
        pnl = bal * risk_pct * r
        bal += pnl
        ypnl += pnl
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    bal, carry, t = settle(bal, ypnl, carry)
    return bal, dd, taxes + t


def settle(bal, ypnl, carry):
    g = ypnl / EURUSD
    if g <= 0:
        return bal, carry - g, 0.0
    used = min(carry, g)
    t = CGT * max(0.0, g - used - EXEMPT_EUR) * EURUSD
    return bal - t, carry - used, t


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    df = load_gold()
    d = daily_bars(df)
    print("daily bars", d.index[0], "->", d.index[-1], len(d))
    rows, trades = [], {}
    for cfg in GRID:
        tr = run(df, d, *cfg)
        trades[cfg] = tr
        sel = part(tr, SEL0, CUT - pd.Timedelta(days=1))
        h1, h2 = part(sel, SEL0, MID), part(sel, MID, CUT)
        row = dict(fam=cfg[0], p=cfg[1], trend=cfg[2], exit=cfg[3], k=cfg[4], sides=cfg[5])
        for name, sub in (("sel", sel), ("h1", h1), ("h2", h2), ("3y", part(tr, CUT, END)), ("1518", part(tr, S0, S1))):
            for kk, v in summ(sub.r if len(sub) else []).items():
                row[f"{kk}_{name}"] = v
        rows.append(row)
    g = pd.DataFrame(rows)
    g.to_csv(RES / "high_wr_grid.csv", index=False)
    ok = g[(g.n_sel >= 40) & (g.win_sel >= 0.60) & (g.avg_h1 > 0) & (g.avg_h2 > 0)].sort_values("t_sel", ascending=False)
    print(f"rules tested {len(g)}; >=60% win AND profitable in both halves of 2019-23: {len(ok)}")
    cols = ["fam", "p", "trend", "exit", "k", "sides", "n_sel", "win_sel", "avg_sel", "t_sel",
            "n_3y", "win_3y", "avg_3y", "n_1518", "win_1518", "avg_1518"]
    print(ok[cols].head(20).round(3).to_string(index=False))
    top = ok.head(20)
    print(f"\nTop-20 average  2019-23: win {top.win_sel.mean():.0%} avg {top.avg_sel.mean():+.3f}R | "
          f"last 3y: win {top.win_3y.mean():.0%} avg {top.avg_3y.mean():+.3f}R | "
          f"2015-18: win {top.win_1518.mean():.0%} avg {top.avg_1518.mean():+.3f}R")
    best = ok.iloc[0]
    cfg = (best.fam, int(best.p), int(best.trend), best.exit, int(best.k), best.sides)
    json.dump(list(cfg), open(RES / "high_wr_winner.json", "w"))
    tr = trades[cfg]
    print("\nWINNER (chosen on 2019 - Sep 2023 only):", cfg)
    for label, a, b in (("2019-Sep 2023 (selection)", SEL0, CUT - pd.Timedelta(days=1)),
                        ("Oct 2023-Sep 2026 (last 3 years)", CUT, END), ("2015-2018 (stress)", S0, S1)):
        sub = part(tr, a, b)
        if len(sub) < 3:
            print(f"  {label}: too few trades ({len(sub)})")
            continue
        m, rnd, p = drift_test(df, d, sub)
        b0, dd0, _ = account(sub, "r")
        b1, dd1, tax = account(sub, "r")
        bsf, _, _ = account(sub, "r_noswap")
        print(f"  {label}: {len(sub)} trades, win {np.mean(sub.r > 0):.0%}, avg {sub.r.mean():+.3f}R, "
              f"longs {np.mean(sub.side > 0):.0%}, stops hit {np.mean(sub.reason == 'stop'):.0%}, avg hold {sub.hold.mean():.1f}d")
        print(f"      $1,000 -> ${b1:,.0f} after swap+tax (tax ${tax:,.0f}), ${bsf:,.0f} if swap-free; max DD {dd1:.0%}")
        print(f"      drift test: strategy {m:+.3%}/trade vs random same-length {rnd:+.3%}  (p = {p:.3f})")
