"""Gotobi lab, round 2: stress-test the only add-ons that improved BOTH the design and the hold-out period
in round 1 (gotobi_lab.py): a take-profit on the long, and a short right after the 09:55 JST fix.

  1. Take-profit neighbourhood (a real effect is a plateau, not a spike), by year, and on control days.
  2. Post-fix short: exit time x stop x late entry, BoJ days, by year, and the same trade on control days
     (if it works every day it is a Tokyo-fix effect, not a gotobi one; if only on gotobi days, it is gotobi flow).
  3. The combination, scored like round 1 plus walk-forward, a paired bootstrap of the Sharpe gain, and by year.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import gotobi_lab as L
from gotobi_lab import Market, max_dd_r, minutes, run_leg, sharpe

RNG = np.random.default_rng(17)


def control_days(S: pd.DataFrame) -> pd.DatetimeIndex:
    """Business days with a Tokyo fix that are not gotobi days (no weekends, Japanese or bank holidays)."""
    import holidays
    jp = holidays.Japan(years=range(2015, 2028))
    days = pd.bdate_range(S.gotobi.iloc[0], S.gotobi.iloc[-1])
    keep = [d for d in days if d.date() not in jp and (d.month, d.day) not in ((12, 31), (1, 2), (1, 3))]
    return pd.DatetimeIndex(keep).difference(pd.DatetimeIndex(S.gotobi))


def stats(r: np.ndarray, per_year: float, years: np.ndarray, split: np.ndarray) -> str:
    return (f"design {sharpe(r[~split], per_year):5.2f} | hold-out {sharpe(r[split], per_year):5.2f} | "
            f"all {sharpe(r, per_year):5.2f} | avg {r.mean():+.3f}R | DD {max_dd_r(r):4.1f}R")


def leg_t(x: np.ndarray) -> float:
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))) if len(x) > 2 else np.nan


def main():
    M = Market()
    S = L.load_slots()
    F = L.features(M, S)
    n = len(S)
    per_year = n / ((S.gotobi.iloc[-1] - S.gotobi.iloc[0]).days / 365.25)
    years = S.year.values
    hold = (S.gotobi >= L.SPLIT).values
    base = [run_leg(M, S.m_in[k], S.m_exit[k], 1) for k in range(n)]
    rb = np.array([b.r for b in base])
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p(f"BASE           {stats(rb, per_year, years, hold)}")

    # ---------------------------------------------------------------- 1. take-profit neighbourhood
    p("\n=== 1. Take-profit on the long (55-pip stop kept). Sharpe; Δ = change vs base")
    tps = (15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 90)
    tp_r = {}
    for tp in tps:
        legs = [run_leg(M, S.m_in[k], S.m_exit[k], 1, tp=tp) for k in range(n)]
        r = np.array([l.r for l in legs])
        tp_r[tp] = r
        hit = np.mean([l.why == "target" for l in legs])
        p(f"  TP {tp:3d}: hit {hit:4.0%} | {stats(r, per_year, years, hold)} | Δ design "
          f"{sharpe(r[~hold], per_year) - sharpe(rb[~hold], per_year):+.2f} hold-out "
          f"{sharpe(r[hold], per_year) - sharpe(rb[hold], per_year):+.2f}")
    p("  by year, R gained by TP 30 vs base: " + "  ".join(
        f"{y % 100:02d}:{tp_r[30][years == y].sum() - rb[years == y].sum():+.1f}" for y in sorted(set(years))))
    p("  by year, R gained by TP 50 vs base: " + "  ".join(
        f"{y % 100:02d}:{tp_r[50][years == y].sum() - rb[years == y].sum():+.1f}" for y in sorted(set(years))))

    # control days: does a take-profit also help the same long on non-gotobi days? (a path property of the hour)
    C = control_days(S)
    c_in = [minutes(d - pd.Timedelta(hours=9, minutes=5)) for d in C]            # 15:55 UTC the day before
    c_in = [m if M.t[M.at(m)] - m <= 30 else int(M.t[M.at(m)]) + 15 for m in c_in]
    c_out = [minutes(d + pd.Timedelta(minutes=54)) for d in C]
    cb = np.array([run_leg(M, a, b, 1).r for a, b in zip(c_in, c_out)])
    c30 = np.array([run_leg(M, a, b, 1, tp=30).r for a, b in zip(c_in, c_out)])
    p(f"  control days ({len(C)}): plain long avg {cb.mean():+.3f}R (t {leg_t(cb):+.2f}); with TP 30 avg "
      f"{c30.mean():+.3f}R (t {leg_t(c30):+.2f}); TP 30 gain on control days {c30.mean() - cb.mean():+.3f}R/trade vs "
      f"{tp_r[30].mean() - rb.mean():+.3f}R on gotobi days")

    # ---------------------------------------------------------------- 2. post-fix short
    p("\n=== 2. Short after the 09:55 JST fix (own result per trade in R, t-stat; then base + short)")
    p(f"  {'variant':40s} {'avg R':>7} {'t':>6} {'win':>4} | {'t design':>8} {'t hold':>6} | base + short: design / hold-out Sharpe")
    grid = [(mm, st, late) for mm in (20, 30, 45, 60, 90, 120) for st in (55,) for late in (0,)]
    grid += [(60, st, 0) for st in (20, 30)] + [(60, 55, late) for late in (1, 2, 5)]
    short = {}
    for mm, st, late in grid:
        legs = [run_leg(M, S.m_fix[k] + late, S.m_fix[k] + mm, -1, stop=st) for k in range(n)]
        r = np.array([l.r for l in legs])
        short[(mm, st, late)] = (legs, r)
        comb = rb + r
        p(f"  {f'{mm} min, stop {st}, enter +{late} min':40s} {r.mean():+7.3f} {leg_t(r):+6.2f} {np.mean(r > 0):4.0%} | "
          f"{leg_t(r[~hold]):+8.2f} {leg_t(r[hold]):+6.2f} | {sharpe(comb[~hold], per_year):5.2f} / {sharpe(comb[hold], per_year):5.2f}")
    s60 = short[(60, 55, 0)][1]
    boj = F.boj_day.values
    p(f"  60-min short on BoJ decision days: n {boj.sum()}, avg {s60[boj].mean():+.3f}R; other days {s60[~boj].mean():+.3f}R")
    p("  by year, 60-min short (sum R): " + "  ".join(f"{y % 100:02d}:{s60[years == y].sum():+.1f}" for y in sorted(set(years))))
    p(f"  correlation of the long and the short (per slot): {np.corrcoef(rb, s60)[0, 1]:+.2f}")
    # placebo: the same short on every non-gotobi fix day
    c_fix = [minutes(d + pd.Timedelta(minutes=55)) for d in C]
    cs = np.array([run_leg(M, m, m + 60, -1).r for m in c_fix])
    cy = np.array([d.year for d in C])
    p(f"  control days: 60-min post-fix short avg {cs.mean():+.3f}R (t {leg_t(cs):+.2f}, n {len(cs)}); gotobi days "
      f"{s60.mean():+.3f}R (t {leg_t(s60):+.2f}); difference t "
      f"{(s60.mean() - cs.mean()) / np.sqrt(s60.var(ddof=1) / len(s60) + cs.var(ddof=1) / len(cs)):+.2f}")
    p("  control-day short by year (avg R): " + "  ".join(f"{y % 100:02d}:{cs[cy == y].mean():+.3f}" for y in sorted(set(cy))))

    # ---------------------------------------------------------------- 3. combinations
    p("\n=== 3. Combinations (per slot: long [+ short]); paired bootstrap of the Sharpe gain over base")
    combos = {
        "base + short 60": rb + s60,
        "TP 30": tp_r[30],
        "TP 30 + short 60": tp_r[30] + s60,
        "TP 40 + short 60": tp_r[40] + s60,
        "TP 50 + short 60": tp_r[50] + s60,
        "TP 30 + short 30": tp_r[30] + short[(30, 55, 0)][1],
        "TP 30 + short 120": tp_r[30] + short[(120, 55, 0)][1],
        "TP 30 + half short 60": tp_r[30] + 0.5 * s60,
        "TP 30 + short 60, skip short on BoJ days": tp_r[30] + np.where(boj, 0, s60),
    }
    for name, r in combos.items():
        boots = []
        for _ in range(2000):
            i = RNG.integers(0, n, n)
            boots.append(sharpe(r[i], per_year) - sharpe(rb[i], per_year))
        boots = np.array(boots)
        p(f"  {name:42s} {stats(r, per_year, years, hold)} | gain {sharpe(r, per_year) - sharpe(rb, per_year):+.2f} "
          f"(90% CI {np.percentile(boots, 5):+.2f} to {np.percentile(boots, 95):+.2f}, P(gain<=0) {np.mean(boots <= 0):.1%})")
    best = combos["TP 30 + short 60"]
    p("  by year, sum R  base / TP 30 + short 60: " + "  ".join(
        f"{y % 100:02d}: {rb[years == y].sum():+.1f}/{best[years == y].sum():+.1f}" for y in sorted(set(years))))
    yb = pd.Series(rb).groupby(years).sum()
    yc = pd.Series(best).groupby(years).sum()
    p(f"  years the combination beat the base: {int((yc > yb).sum())}/{len(yb)}; losing years base {int((yb < 0).sum())}, "
      f"combination {int((yc < 0).sum())}")
    pd.to_pickle(dict(rb=rb, tp=tp_r, short={k: v[1] for k, v in short.items()}, combos=combos, years=years,
                      gotobi=S.gotobi.values), L.RES / "lab2_results.pkl")
    (L.RES / "lab2_report.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
