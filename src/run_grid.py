"""Run every rule variant on every symbol; pick on 2019-2023, judge on 2024-2026."""
import sys
from concurrent.futures import ProcessPoolExecutor
from itertools import product
from pathlib import Path

import pandas as pd

from backtest import Params, load, run, stats

OUT = Path(__file__).resolve().parent.parent / "results"
SYMS = ["XAUUSDm", "EURUSDm", "GBPUSDm", "USDJPYm"]
SPLIT = pd.Timestamp("2024-01-01").date()
WINDOWS = {"asia": dict(win_start=7, win_end=10, flat=16),     # London open kill zone
           "pdhl": dict(win_start=7, win_end=16, flat=20)}     # London + NY overlap


def variants():
    for model, confirm, target in product(["asia", "pdhl"], ["reclaim", "mss"], ["1R", "2R", "3R", "range"]):
        yield Params(model=model, confirm=confirm, target=target, **WINDOWS[model])


def bias_slices(tr):
    """Same trades, split by whether they agreed with the daily trend (prior close vs SMA20)."""
    if not len(tr):
        return {"none": tr, "with": tr, "against": tr}
    t = tr[tr["has_trend"] == 1]
    return {"none": tr, "with": t[t["with_trend"] == 1], "against": t[t["with_trend"] == 0]}


def one_symbol(sym):
    df = load(sym)
    rows, all_trades = [], []
    for p in variants():
        base = run(sym, p, df)
        if len(base):
            base["sym"], base["variant"] = sym, f"{p.model}|{p.confirm}|{p.target}"
            all_trades.append(base)
        for bias, tr in bias_slices(base).items():
            tag = f"{p.model}|{p.confirm}|{p.target}|{bias}"
            for part, sub in (("IS", tr[tr["day"] < SPLIT] if len(tr) else tr),
                              ("OOS", tr[tr["day"] >= SPLIT] if len(tr) else tr)):
                rows.append(dict(sym=sym, variant=tag, part=part, **stats(sub)))
        print(sym, p, "done", flush=True)
    return pd.DataFrame(rows), pd.concat(all_trades) if all_trades else pd.DataFrame()


if __name__ == "__main__":
    syms = sys.argv[1:] or SYMS
    OUT.mkdir(exist_ok=True)
    with ProcessPoolExecutor(len(syms)) as ex:
        res = list(ex.map(one_symbol, syms))
    grid = pd.concat([r[0] for r in res])
    trades = pd.concat([r[1] for r in res])
    grid.to_csv(OUT / "grid.csv", index=False)
    trades.to_parquet(OUT / "trades.parquet")
    pd.set_option("display.width", 200, "display.max_rows", 500)
    wide = grid.pivot_table(index=["sym", "variant"], columns="part",
                            values=["n", "win", "avgR", "PF", "totR", "maxDD_R", "t"])
    print(wide.round(2).to_string())
