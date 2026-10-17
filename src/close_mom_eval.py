"""Into-the-close momentum: economics at today's Exness spreads, by year, and for a EUR 100 account.

Reads results/close_mom_trades.parquet (written by close_mom.py).
  today cost = median round-trip spread of the last 3 months in the data + 0.2 bp slippage per side
  rules: ALL days (published rule) and BIG days (|signal| above its trailing 250-day median; the paper's
         mechanism - dealer hedging grows with the size of the move - written into close_mom.py before results)
"""
import sys

import numpy as np
import pandas as pd

from close_mom import RES, SLIP

CGT, EXEMPT, EURUSD = 0.33, 1270.0, 1.17


def account(r, lev, start=100.0):
    """daily compounding at fixed notional leverage (fraction of equity), Irish CGT once a year."""
    bal, peak, dd, ypnl, year = start, start, 0.0, 0.0, None
    for d, x in r.items():
        if year is not None and d.year != year:
            if ypnl > 0:
                bal -= CGT * max(0.0, ypnl - EXEMPT)
            ypnl = 0.0
        year = d.year
        pnl = bal * lev * x
        bal += pnl
        ypnl += pnl
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
        if bal <= 1:
            return 0.0, 1.0
    if ypnl > 0:
        bal -= CGT * max(0.0, ypnl - EXEMPT)
    return bal, dd


if __name__ == "__main__":
    t = pd.read_parquet(RES / "close_mom_trades.parquet")
    syms = sys.argv[1:] or list(t.sym.unique())
    for s in syms:
        x = t[t.sym == s].set_index("day").sort_index()
        recent = x[x.index >= x.index.max() - pd.Timedelta(days=90)]
        cost_now = recent.spread_rt.median() + 2 * SLIP
        sig = x["rod"]
        big = sig.abs() > sig.abs().rolling(250, min_periods=100).median().shift(1)
        print(f"\n=== {s}: today's round-trip cost {cost_now * 1e4:.2f} bp (spread {recent.spread_rt.median() * 1e4:.2f} + slippage)")
        for lab, m in (("ALL days", np.ones(len(x), bool)), ("BIG days", big.to_numpy())):
            g = x.gross_rod[m]
            today = g - cost_now
            y = g.groupby(g.index.year)
            print(f"  {lab}: n {m.sum()}  gross {g.mean() * 1e4:+.2f} bp (t {g.mean() / g.std() * np.sqrt(len(g)):+.2f})  "
                  f"at today's cost {today.mean() * 1e4:+.2f} bp (t {today.mean() / today.std() * np.sqrt(len(today)):+.2f}, "
                  f"hit {(today > 0).mean():.1%}, Sharpe {today.mean() / today.std() * np.sqrt(252 * m.mean()):+.2f})")
            print("     gross by year: " + " ".join(f"{k % 100:02d}:{v * 1e4:+.1f}" for k, v in y.mean().items()))
            print("     today-cost by year: " + " ".join(f"{k % 100:02d}:{(v - cost_now) * 1e4:+.1f}" for k, v in y.mean().items()))
            full = pd.Series(0.0, index=x.index)
            full[m] = today
            for lev in (5, 10, 20):
                b, dd = account(full, lev)
                b3, dd3 = account(full[full.index >= "2023-10-01"], lev)
                print(f"     leverage {lev:2d}x: EUR 100 -> {b:8,.0f} over {x.index.min().year}-{x.index.max().year} (max DD {dd:.0%}) | "
                      f"last 3y -> {b3:7,.0f} (DD {dd3:.0%})")
