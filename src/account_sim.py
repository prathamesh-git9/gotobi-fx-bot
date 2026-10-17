"""Replay chosen variants on a real-sized account: 1% risk, 0.01-lot steps, gold = 100 oz/lot."""
import numpy as np
import pandas as pd

TR = pd.read_parquet(__import__("pathlib").Path(__file__).resolve().parent.parent / "results" / "trades.parquet")
OZ_PER_LOT, LOT_STEP, MIN_LOT = 100, 0.01, 0.01


def select(variant, trend_only=False, start=None):
    t = TR[(TR.sym == "XAUUSDm") & (TR.variant == variant)].sort_values("time")
    if trend_only:
        t = t[(t.has_trend == 1) & (t.with_trend == 1)]
    if start:
        t = t[t.day >= pd.Timestamp(start).date()]
    return t


def replay(t, balance=1000.0, risk_pct=0.01, max_min_lot_risk=0.02):
    eq, peak, maxdd, skipped = [balance], balance, 0.0, 0
    for risk_px, r in zip(t.risk.to_numpy(), t.r.to_numpy()):
        usd_per_lot = risk_px * OZ_PER_LOT                  # $ lost per 1.00 lot if stopped
        lots = np.floor(balance * risk_pct / usd_per_lot / LOT_STEP) * LOT_STEP
        if lots < MIN_LOT:
            if MIN_LOT * usd_per_lot > balance * max_min_lot_risk:
                skipped += 1
                continue
            lots = MIN_LOT
        balance += r * lots * usd_per_lot
        peak = max(peak, balance)
        maxdd = max(maxdd, 1 - balance / peak)
        eq.append(balance)
    return balance, maxdd, skipped, len(eq) - 1


def worst_streak(r):
    s = best = 0
    for x in r:
        s = s + 1 if x < 0 else 0
        best = max(best, s)
    return best


def bootstrap_year(t, n_sims=20000, seed=0):
    rng = np.random.default_rng(seed)
    per_year = len(t) / ((t.day.iloc[-1] - t.day.iloc[0]).days / 365.25)
    k = int(round(per_year))
    r = t.r.to_numpy()
    out = np.empty(n_sims)
    dd = np.empty(n_sims)
    for i in range(n_sims):
        path = 1000 * np.cumprod(1 + 0.01 * rng.choice(r, k))   # 1% risk, compounding
        out[i] = path[-1]
        dd[i] = (1 - path / np.maximum.accumulate(path)).max()
    return k, out, dd


if __name__ == "__main__":
    cases = [("A: PDH/PDL sweep, reclaim, 3R, with-trend (the 2019-23 pick)", "pdhl|reclaim|3R", True),
             ("B: PDH/PDL sweep, reclaim, 3R, all trades", "pdhl|reclaim|3R", False),
             ("C: PDH/PDL sweep, reclaim, opposite-side target", "pdhl|reclaim|range", False)]
    for name, v, tf in cases:
        print("\n==", name)
        for start in (None, "2024-01-01"):
            t = select(v, tf, start)
            bal, dd, sk, n = replay(t)
            label = "2019-01 -> 2026-09" if start is None else "2024-01 -> 2026-09"
            print(f"  $1000 {label}: final ${bal:,.0f}  maxDD {dd:.0%}  trades {n} (skipped {sk})  "
                  f"win {np.mean(t.r > 0):.0%}  worst losing streak {worst_streak(t.r)}")
        t = select(v, tf)
        k, out, dd = bootstrap_year(t)
        print(f"  Next 12 months (~{k} trades, bootstrap of 2019-26 trades):  "
              f"P(lose money) {np.mean(out < 1000):.0%}  P(down >=20%) {np.mean(out < 800):.0%}  "
              f"median ${np.median(out):,.0f}  5th pct ${np.percentile(out, 5):,.0f}  "
              f"95th pct ${np.percentile(out, 95):,.0f}  P(drawdown >=25% along the way) {np.mean(dd >= .25):.0%}")
