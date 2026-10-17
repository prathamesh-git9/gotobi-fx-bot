"""Pick a gold rule on Jan 2019 - Sep 2023 (must be profitable in BOTH halves), then run it once on
Oct 2023 - Sep 2026 with a $1,000 account, every cost, and Irish capital gains tax."""
import json
import sys
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

from gold_rnd import PLANS

RES = Path(__file__).resolve().parent.parent / "results"
DATA = RES.parent / "data"
CUT, MID, END = pd.Timestamp("2023-10-01"), pd.Timestamp("2021-07-01"), pd.Timestamp("2026-09-30")
F = ["trend", "sane", "quick", "strong", "shallow", "mss_too", "lon_open", "ny", "midweek", "no_nfp",
     "vol_hi", "premium", "above_open", "stacked", "asia_tight", "pd_against"]
MODELS = {"asia": ["asia"], "pdhl": ["pdhl"], "both": ["asia", "pdhl"]}
MIN_N = 100
CGT, EXEMPT_EUR = 0.33, 1270.0


def load_sig(name):
    s = pd.read_parquet(RES / f"gold_rnd_{name}.parquet")
    s["day"] = pd.to_datetime(s["day"])
    return s.sort_values("time")


def search(s):
    rows = []
    for ek in ("reclaim", "mss"):
        for mn, models in MODELS.items():
            base = s[(s.entry_kind == ek) & s.model.isin(models)]
            sel = base[base.day < CUT]
            hold = base[(base.day >= CUT) & (base.day <= END)]
            first = (sel.day < MID).to_numpy()
            fs_sel = {f: sel[f].to_numpy(bool) for f in F}
            fs_hold = {f: hold[f].to_numpy(bool) for f in F}
            R_sel = {p: sel[p].to_numpy() for p in PLANS}
            R_hold = {p: hold[p].to_numpy() for p in PLANS}
            for k in range(4):
                for combo in combinations(F, k):
                    ma = np.ones(len(sel), bool)
                    mb = np.ones(len(hold), bool)
                    for f in combo:
                        ma &= fs_sel[f]
                        mb &= fs_hold[f]
                    n = ma.sum()
                    if n < MIN_N:
                        continue
                    for p in PLANS:
                        r = R_sel[p][ma]
                        h1, h2 = R_sel[p][ma & first], R_sel[p][ma & ~first]
                        rh = R_hold[p][mb]
                        rows.append(dict(entry=ek, model=mn, filters="+".join(combo) or "-", plan=p, n_sel=n,
                                         win_sel=(r > 0).mean(), avgR_sel=r.mean(),
                                         t_sel=r.mean() / (r.std(ddof=1) / np.sqrt(n)),
                                         h1=h1.mean() if len(h1) else np.nan, h2=h2.mean() if len(h2) else np.nan,
                                         n_3y=len(rh), win_3y=(rh > 0).mean() if len(rh) else np.nan,
                                         avgR_3y=rh.mean() if len(rh) else np.nan))
    return pd.DataFrame(rows)


def subset(s, cfg):
    x = s[(s.entry_kind == cfg["entry"]) & s.model.isin(MODELS[cfg["model"]])]
    for f in ([] if cfg["filters"] == "-" else cfg["filters"].split("+")):
        x = x[x[f]]
    return x


def eurusd_by_year():
    e = pd.read_parquet(DATA / "EURUSDm_m1.parquet", columns=["bclose"])
    return e["bclose"].groupby(e.index.year).mean()


def account(tr, plan, start=1000.0, risk_pct=0.01, tax=True):
    """Compounding 1% risk, 0.01-lot steps (gold: 100 oz per lot). Irish CGT settled each 31 Dec."""
    fx = eurusd_by_year()
    bal, peak, dd = start, start, 0.0
    year, year_pnl, carry_loss, taxes, log = None, 0.0, 0.0, 0.0, []

    def settle(y):
        nonlocal bal, year_pnl, carry_loss, taxes
        gain_eur = year_pnl / fx.get(y, fx.iloc[-1])
        t = 0.0
        if gain_eur > 0:
            used = min(carry_loss, gain_eur)
            carry_loss -= used
            taxable = max(0.0, gain_eur - used - EXEMPT_EUR)
            t = CGT * taxable * fx.get(y, fx.iloc[-1])
        else:
            carry_loss += -gain_eur
        if tax:
            bal -= t
            taxes += t
        log.append((y, round(year_pnl, 2), round(t, 2), round(bal, 2)))
        year_pnl = 0.0

    for t, risk, r in tr[["time", "risk", plan]].itertuples(index=False):
        if year is not None and t.year != year:
            settle(year)
        year = t.year
        per_lot = risk * 100
        lots = np.floor(bal * risk_pct / per_lot / 0.01) * 0.01
        if lots < 0.01:
            if 0.01 * per_lot > bal * 0.02:
                continue
            lots = 0.01
        pnl = r * lots * per_lot
        bal += pnl
        year_pnl += pnl
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    settle(year)
    return bal, dd, taxes, log


if __name__ == "__main__":
    pd.set_option("display.width", 240)
    std = load_sig("XAUUSDm")
    g = search(std)
    g.to_csv(RES / "gold_search.csv", index=False)
    stable = g[(g.h1 > 0) & (g.h2 > 0)].sort_values("t_sel", ascending=False)
    print(f"configs with >= {MIN_N} trades: {len(g)}   profitable in both halves of 2019-23: {len(stable)} "
          f"({len(stable) / len(g):.1%})")
    print("\nExit plans on ALL gold signals, 2019-Sep 2023 (win rate vs average R):")
    sel = std[std.day < CUT]
    print(pd.DataFrame({p: [(sel[p] > 0).mean(), sel[p].mean()] for p in PLANS}, index=["win", "avgR"]).round(3).to_string())
    print("\nTop 20 stable rules (by selection t-stat) and what they did in the last 3 years:")
    print(stable.head(20).round(3).to_string(index=False))
    top = stable.head(20)
    print(f"Top-20 average: selection {top.avgR_sel.mean():+.3f}R (win {top.win_sel.mean():.0%}) -> "
          f"last 3y {top.avgR_3y.mean():+.3f}R (win {top.win_3y.mean():.0%})")

    win = stable.iloc[0][["entry", "model", "filters", "plan"]].to_dict()
    json.dump(win, open(RES / "gold_winner.json", "w"))
    print("\nWINNER (chosen on 2019 - Sep 2023 only):", win)
    for name, label in (("XAUUSDm", "Standard account (spread + $0.10/oz slippage)"),
                        ("XAUUSD_Raw_Spread", "Raw Spread account ($7/lot commission + raw spread + $0.10/oz slippage)")):
        try:
            s = load_sig(name)
        except FileNotFoundError:
            print(f"  ({label}: no data yet)")
            continue
        tr = subset(s, win)
        hold = tr[(tr.day >= CUT) & (tr.day <= END)]
        r = hold[win["plan"]]
        print(f"\n  {label}")
        print(f"  last 3y: {len(hold)} trades, win rate {np.mean(r > 0):.0%}, avg {r.mean():+.3f}R, "
              f"avg cost per trade {(hold.spread_r + hold.cost_r).mean():.3f}R")
        for start in (1000, 10000):
            b0, dd0, _, _ = account(hold, win["plan"], start, tax=False)
            b1, dd1, tx, log = account(hold, win["plan"], start, tax=True)
            print(f"  ${start:,} -> before tax ${b0:,.0f} | after Irish CGT ${b1:,.0f} (tax paid ${tx:,.0f})  "
                  f"max drawdown {dd1:.0%}")
            if start == 1000:
                print("    year, P&L $, tax $, balance $:", log)
