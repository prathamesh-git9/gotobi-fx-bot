"""Pick a 5-min gold rule (>=60% win, profitable in both halves of 2019-Sep 2023 at today's costs),
then test it once on Oct 2023-Sep 2026 (real costs) and 2016-2018 (never used)."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from m5_lab import HS, SLS, TPS, configs, run_config

RES = Path(__file__).resolve().parent.parent / "results"
P = {"sel": ("2019-01-01", "2023-09-30"), "h1": ("2019-01-01", "2021-06-30"), "h2": ("2021-07-01", "2023-09-30"),
     "3y": ("2023-10-01", "2026-09-30"), "1618": ("2016-01-01", "2018-12-31")}


def stats(r):
    r = np.asarray(r)
    if len(r) < 10:
        return len(r), np.nan, np.nan, np.nan
    return len(r), (r > 0).mean(), r.mean(), r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    m = pd.read_parquet(RES.parent / "data" / "XAU_m5.parquet")
    rows = []
    for cfg in configs():
        for tp in TPS:
            for sl in SLS:
                for H in HS:
                    t = run_config(m, cfg, tp, sl, H, "modern")
                    rec = dict(fam=cfg[0], p=cfg[1], sess=cfg[2], trend=cfg[3], sides=cfg[4], tp=tp, sl=sl, H=H)
                    for k, (a, b) in P.items():
                        sub = t[(t.time >= np.datetime64(a)) & (t.time < np.datetime64(b) + np.timedelta64(1, "D"))]
                        n, w, avg, ts = stats(sub.r)
                        rec.update({f"n_{k}": n, f"win_{k}": w, f"avg_{k}": avg, f"t_{k}": ts})
                    rows.append(rec)
    g = pd.DataFrame(rows)
    g.to_csv(RES / "m5_grid.csv", index=False)
    yrs = 4.75
    ok = g[(g.n_sel >= 150) & (g.win_sel >= 0.60) & (g.avg_h1 > 0) & (g.avg_h2 > 0)].sort_values("t_sel", ascending=False)
    print(f"rules tested {len(g)}; >=60% win + profitable both halves (today's costs): {len(ok)}")
    print(f"rules with >=60% win at all in 2019-23: {(g.win_sel >= 0.6).sum()}, of which avg R > 0: {((g.win_sel >= 0.6) & (g.avg_sel > 0)).sum()}")
    cols = ["fam", "p", "sess", "trend", "sides", "tp", "sl", "H", "n_sel", "win_sel", "avg_sel", "t_sel",
            "n_3y", "win_3y", "avg_3y", "n_1618", "win_1618", "avg_1618"]
    print(ok[cols].head(25).round(3).to_string(index=False))
    top = ok.head(20)
    if len(top):
        print(f"Top-20 average: 2019-23 win {top.win_sel.mean():.0%} avg {top.avg_sel.mean():+.3f}R | last 3y win "
              f"{top.win_3y.mean():.0%} avg {top.avg_3y.mean():+.3f}R | 2016-18 win {top.win_1618.mean():.0%} avg {top.avg_1618.mean():+.3f}R")
        json.dump(ok.iloc[0][["fam", "p", "sess", "trend", "sides", "tp", "sl", "H"]].to_dict(),
                  open(RES / "m5_winner.json", "w"), default=float)
