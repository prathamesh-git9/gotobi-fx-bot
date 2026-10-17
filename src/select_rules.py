"""Pick the confluence rule on Jan 2019 - Sep 2023 only, then judge it on Oct 2023 - Sep 2026."""
from itertools import combinations

import numpy as np
import pandas as pd

s = pd.read_parquet("../results/signals.parquet")
s["day"] = pd.to_datetime(s["day"])
CUT = pd.Timestamp("2023-10-01")
F = ["trend", "quick", "shallow", "strong", "mss", "room", "sane"]
R = [c for c in s.columns if c.startswith("r_")]
UNIV = {"gold": ["XAUUSDm"], "eurusd": ["EURUSDm"], "gbpusd": ["GBPUSDm"], "usdjpy": ["USDJPYm"],
        "all4": ["XAUUSDm", "EURUSDm", "GBPUSDm", "USDJPYm"]}
MODELS = {"asia": ["asia"], "pdhl": ["pdhl"], "both": ["asia", "pdhl"]}


def score(r):
    r = np.asarray(r)
    if len(r) < 2:
        return np.nan, np.nan
    return r.mean(), r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))


rows = []
for un, syms in UNIV.items():
    for mn, models in MODELS.items():
        base = s[s.sym.isin(syms) & s.model.isin(models)]
        for k in range(0, 4):
            for fs in combinations(F, k):
                sub = base
                for f in fs:
                    sub = sub[sub[f]]
                a, b = sub[sub.day < CUT], sub[sub.day >= CUT]
                for rc in R:
                    m_a, t_a = score(a[rc])
                    m_b, t_b = score(b[rc])
                    rows.append(dict(universe=un, model=mn, filters="+".join(fs) or "-", exit=rc,
                                     n_sel=len(a), avgR_sel=m_a, t_sel=t_a, n_3y=len(b), avgR_3y=m_b, t_3y=t_b))
g = pd.DataFrame(rows)
g.to_csv("../results/confluence_search.csv", index=False)
ok = g[g.n_sel >= 100].sort_values("t_sel", ascending=False)
print("configs searched:", len(g), " with >=100 selection trades:", len(ok))
print("share with avgR_sel > 0:", f"{(ok.avgR_sel > 0).mean():.1%}")
pd.set_option("display.width", 220)
print("\nTop 20 by selection-period t-stat, and what they then did in the last 3 years:")
print(ok.head(20).round(3).to_string(index=False))
top = ok.head(20)
print(f"\nTop-20 average: selection {top.avgR_sel.mean():+.3f}R  ->  last 3y {top.avgR_3y.mean():+.3f}R")
print("Winner:", ok.iloc[0][["universe", "model", "filters", "exit"]].to_dict())
