"""Choose the order-block / order-flow / heat-map rule on Jan 2019 - Sep 2023, then judge it on
Oct 2023 - Sep 2026 with a $1,000 account. The holdout is never used for choosing."""
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

RES = Path(__file__).resolve().parent.parent / "results"
s = pd.read_parquet(RES / "ict_signals.parquet")
s["day"] = pd.to_datetime(s["day"])
CUT, END = pd.Timestamp("2023-10-01"), pd.Timestamp("2026-09-30")
F = ["trend", "sane", "quick", "fvg", "of_spike", "of_absorb", "of_disp", "heat", "magnet"]
R = ["r_2", "r_3", "r_3be", "r_range"]
UNIV = {"gold": ["XAUUSDm"], "eurusd": ["EURUSDm"], "gbpusd": ["GBPUSDm"], "usdjpy": ["USDJPYm"],
        "all4": ["XAUUSDm", "EURUSDm", "GBPUSDm", "USDJPYm"]}
MODELS = {"asia": ["asia"], "pdhl": ["pdhl"], "both": ["asia", "pdhl"]}
MIN_N = 80


def tstat(r):
    r = r[~np.isnan(r)]
    if len(r) < 2 or r.std(ddof=1) == 0:
        return len(r), np.nan, np.nan
    return len(r), r.mean(), r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))


def search():
    rows = []
    for un, syms in UNIV.items():
        for mn, models in MODELS.items():
            for ek in ("ob", "mkt"):
                base = s[s.sym.isin(syms) & s.model.isin(models) & (s.entry_kind == ek)]
                a_all, b_all = base[base.day < CUT], base[(base.day >= CUT) & (base.day <= END)]
                for k in range(4):
                    for fs in combinations(F, k):
                        ma = np.ones(len(a_all), bool)
                        mb = np.ones(len(b_all), bool)
                        for f in fs:
                            ma &= a_all[f].to_numpy(bool)
                            mb &= b_all[f].to_numpy(bool)
                        for rc in R:
                            na, avg_a, t_a = tstat(a_all[rc].to_numpy(float)[ma])
                            nb, avg_b, t_b = tstat(b_all[rc].to_numpy(float)[mb])
                            rows.append(dict(universe=un, model=mn, entry=ek, filters="+".join(fs) or "-",
                                             exit=rc, n_sel=na, avgR_sel=avg_a, t_sel=t_a,
                                             n_3y=nb, avgR_3y=avg_b, t_3y=t_b))
    return pd.DataFrame(rows)


def lot_value(sym, risk, price):
    """USD lost per 1.00 lot if the stop (risk in price units) is hit."""
    if sym.startswith("XAU"):
        return risk * 100
    if sym.startswith("USDJPY"):
        return risk * 100_000 / price
    return risk * 100_000


def account(trades, rc, start=1000.0, risk_pct=0.01):
    bal, peak, dd, skipped = start, start, 0.0, 0
    for sym, risk, price, r in trades[["sym", "risk", "entry", rc]].itertuples(index=False):
        per_lot = lot_value(sym, risk, price)
        lots = np.floor(bal * risk_pct / per_lot / 0.01) * 0.01
        if lots < 0.01:
            if 0.01 * per_lot > bal * 0.02:
                skipped += 1
                continue
            lots = 0.01
        bal += r * lots * per_lot
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    return bal, dd, skipped


def pick(cfg):
    sub = s[s.sym.isin(UNIV[cfg["universe"]]) & s.model.isin(MODELS[cfg["model"]]) & (s.entry_kind == cfg["entry"])]
    for f in ([] if cfg["filters"] == "-" else cfg["filters"].split("+")):
        sub = sub[sub[f]]
    return sub.dropna(subset=[cfg["exit"]]).sort_values("time")


if __name__ == "__main__":
    pd.set_option("display.width", 230)
    g = search()
    g.to_csv(RES / "ict_search.csv", index=False)
    ok = g[g.n_sel >= MIN_N].sort_values("t_sel", ascending=False)
    print(f"configs {len(g)}, with >= {MIN_N} selection trades {len(ok)}, positive in selection {(ok.avgR_sel > 0).mean():.1%}")

    sel = s[s.day < CUT]
    print("\nWhat each signal does on its own (selection period, all symbols, market entry, 3R):")
    m = sel[sel.entry_kind == "mkt"]
    for f in F:
        on, off = m[m[f]]["r_3"], m[~m[f]]["r_3"]
        print(f"  {f:10s} on {on.mean():+.3f} (n={on.count():5d})   off {off.mean():+.3f}")
    print("\nOrder-block limit entry vs market entry (selection, all symbols, 3R):")
    for ek in ("ob", "mkt"):
        x = sel[sel.entry_kind == ek]["r_3"].dropna()
        print(f"  {ek:4s} n={len(x):5d}  avg {x.mean():+.3f}R  win {np.mean(x > 0):.0%}")

    print("\nTop 20 by selection t-stat -> last 3 years:")
    print(ok.head(20).round(3).to_string(index=False))
    top = ok.head(20)
    print(f"Top-20 average: selection {top.avgR_sel.mean():+.3f}R -> last 3y {top.avgR_3y.mean():+.3f}R")

    win = ok.iloc[0][["universe", "model", "entry", "filters", "exit"]].to_dict()
    json.dump(win, open(RES / "ict_winner.json", "w"))
    tr = pick(win)
    hold = tr[(tr.day >= CUT) & (tr.day <= END)]
    r = hold[win["exit"]]
    print("\nWINNER (chosen on 2019-09/2023 only):", win)
    print(f"Last 3 years: trades {len(hold)}  win {np.mean(r > 0):.0%}  avg {r.mean():+.3f}R  total {r.sum():+.1f}R")
    bal, dd, sk = account(hold, win["exit"])
    print(f"$1,000 Oct 2023 -> Sep 2026: end ${bal:,.0f}   max drawdown {dd:.0%}   skipped {sk}")
    if len(r) > 5:
        print(f"without best 5 trades: {r.sort_values(ascending=False).iloc[5:].sum():+.1f}R")
    rng = np.random.default_rng(1)
    rr = r.to_numpy()
    ends = np.array([1000 * np.prod(1 + 0.01 * rng.choice(rr, len(rr))) for _ in range(20000)])
    print(f"bootstrap: P(end < $1000) {np.mean(ends < 1000):.0%}  median ${np.median(ends):,.0f}  "
          f"5-95% ${np.percentile(ends, 5):,.0f}-${np.percentile(ends, 95):,.0f}")
