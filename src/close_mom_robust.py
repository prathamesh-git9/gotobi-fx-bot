"""Stress tests for the one result that survived: DAX into-the-close momentum on big-move days.

A real effect should change smoothly when the settings move a little; a fluke spikes at one setting.
  entry offset   15 / 20 / 30 (published) / 45 / 60 minutes before the close
  'big' cut-off  signal above the trailing 250-day 30th / 50th (pre-set) / 70th percentile of |signal|
  direction      big up days vs big down days
  recent era     2021-2026 only, with a bootstrap 90% interval for the mean
Costs: today's spread (median of the last 3 months) and the pre-Sep-2025 spread, + 0.2 bp slippage per side.
"""
import sys

import numpy as np
import pandas as pd

from close_mom import SLIP, build

RNG = np.random.default_rng(1)


def big_mask(sig, q):
    a = sig.abs()
    return (a > a.rolling(250, min_periods=100).quantile(q).shift(1)).to_numpy()


def boot(r, n=5000):
    r = np.asarray(r)
    means = RNG.choice(r, (n, len(r))).mean(1)
    return np.percentile(means, [5, 95])


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "DE30"
    base = build(name, 30).set_index("day")
    recent = base[base.index >= base.index.max() - pd.Timedelta(days=90)]
    cost_now = recent.spread_rt.median() + 2 * SLIP
    cost_old = base[base.index < "2025-09-01"].spread_rt.median() + 2 * SLIP
    print(f"{name}: today's cost {cost_now * 1e4:.2f} bp | pre-Sep-2025 cost {cost_old * 1e4:.2f} bp")

    print("\nEntry offset x big cut-off: gross bp per trade (t)   [published: 30 min, 50th pct]")
    print(f"{'offset':>7} | {'all days':>14} | {'big q30':>14} | {'big q50':>14} | {'big q70':>14}")
    for back in (15, 20, 30, 45, 60):
        t = base if back == 30 else build(name, back).set_index("day")
        cells = []
        for q in (None, 0.3, 0.5, 0.7):
            m = np.ones(len(t), bool) if q is None else big_mask(t.rod, q)
            g = t.gross_rod[m]
            cells.append(f"{g.mean() * 1e4:+5.2f} ({g.mean() / g.std() * np.sqrt(len(g)):+4.1f})")
        print(f"{back:>5}m  | " + " | ".join(f"{c:>14}" for c in cells))

    m = big_mask(base.rod, 0.5)
    b = base[m]
    print("\nBig days by direction (gross bp):")
    for lab, mm in (("big UP days -> buy", b.rod > 0), ("big DOWN days -> sell", b.rod < 0)):
        g = b.gross_rod[mm]
        print(f"  {lab:22s} n {mm.sum():4d}  {g.mean() * 1e4:+.2f} bp (t {g.mean() / g.std() * np.sqrt(len(g)):+.2f})")

    print("\nRecent era only (2021 - Sep 2026), big days:")
    r = b[b.index >= "2021-01-01"].gross_rod
    lo, hi = boot(r)
    print(f"  n {len(r)}  gross {r.mean() * 1e4:+.2f} bp (t {r.mean() / r.std() * np.sqrt(len(r)):+.2f}), "
          f"bootstrap 90% interval {lo * 1e4:+.2f} .. {hi * 1e4:+.2f} bp")
    for lab, c in (("today's cost", cost_now), ("pre-Sep-2025 cost", cost_old)):
        x = r - c
        lo, hi = boot(x)
        print(f"  net at {lab:18s}: {x.mean() * 1e4:+.2f} bp (t {x.mean() / x.std() * np.sqrt(len(x)):+.2f}), "
              f"90% interval {lo * 1e4:+.2f} .. {hi * 1e4:+.2f} bp, hit {(x > 0).mean():.1%}")
    half = b[b.index >= "2024-01-01"].gross_rod
    print(f"  2024 - Sep 2026 only: n {len(half)} gross {half.mean() * 1e4:+.2f} bp "
          f"(t {half.mean() / half.std() * np.sqrt(len(half)):+.2f}), net today {(half.mean() - cost_now) * 1e4:+.2f} bp")
