"""Gotobi lab, round 3: money. Exact account replays (the bot's sizing: risk % of equity / loss per lot at the
stop, lots rounded down to 0.01, 1:500 margin cap, its 50% drawdown kill switch) and Monte Carlo blow-up odds,
for the plain bot and the add-ons that survived rounds 1-2.

  python gotobi_lab3.py [short_haircut_pips]

short_haircut_pips: subtract this from every post-fix short (execution delay measured in fix_seconds.py).
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

import gotobi_lab as L
from gotobi_lab import Leg, Market, run_leg

RNG = np.random.default_rng(23)
START, LEV, MAX_MARGIN, KILL_DD = 1000.0, 500, 0.9, 0.5


def strategies(M: Market, S: pd.DataFrame, haircut: float) -> dict[str, list[list[Leg]]]:
    n = len(S)
    long55 = [run_leg(M, S.m_in[k], S.m_exit[k], 1) for k in range(n)]
    long_tp = [run_leg(M, S.m_in[k], S.m_exit[k], 1, tp=30) for k in range(n)]
    short = []
    for k in range(n):
        s = run_leg(M, S.m_fix[k], S.m_fix[k] + 30, -1)
        if haircut:
            s.exit += haircut * L.PIP                     # a short loses when its buy-back price is higher
            s.pnl -= haircut
        short.append(s)
    return {"plain bot (today)": [[a] for a in long55],
            "take-profit +30": [[a] for a in long_tp],
            "plain + post-fix short": [[a, b] for a, b in zip(long55, short)],
            "take-profit +30 + post-fix short": [[a, b] for a, b in zip(long_tp, short)]}


def replay(slots: list[list[Leg]], days: pd.Series, risk: float, start: float = START, kill: bool = True):
    bal, peak, dd, halted, trades, rows = start, start, 0.0, None, 0, []
    for d, legs in zip(days, slots):
        if halted is not None:
            break
        for g in legs:
            equity = round(bal, 2)
            sl = g.sl if g.sl is not None else g.raw - g.side * g.risk * L.PIP
            loss_per_lot = round(L.CONTRACT * g.risk * L.PIP / sl, 2)
            lots = np.floor(equity * risk * g.size / loss_per_lot / 0.01 + 1e-9) * 0.01
            lots = min(lots, np.floor(MAX_MARGIN * equity / (L.CONTRACT / LEV) / 0.01 + 1e-9) * 0.01)
            if lots < 0.01:
                continue
            pnl = lots * L.CONTRACT * (g.exit - g.entry) * g.side / g.exit
            bal += pnl
            trades += 1
            rows.append((d, g.side, lots, pnl, bal))
            peak = max(peak, bal)
            dd = max(dd, 1 - bal / peak)
            if kill and 1 - bal / peak >= KILL_DD:
                halted = d
                break
    return bal, dd, trades, halted, rows


def mc(r_slot: np.ndarray, risk: float, years: float = 3.0, per_year: float = 69.8, paths: int = 20000,
       shift: float = 0.0):
    n = int(round(years * per_year))
    x = RNG.choice(r_slot - shift, (paths, n))
    eq = np.cumprod(1 + risk * x, axis=1)
    dd = (1 - eq / np.maximum.accumulate(eq, axis=1)).max(1)
    return np.median(eq[:, -1]), np.mean(eq[:, -1] < 1), np.mean(dd > 0.3), np.mean(dd > 0.5), np.median(dd)


def main(haircut: float):
    M = Market()
    S = L.load_slots()
    strat = strategies(M, S, haircut)
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p(f"Post-fix short haircut: {haircut} pips per trade. $1,000 USD account, 1:500, kill switch at 50% drawdown.")
    for name, slots in strat.items():
        r = np.array([sum(g.r for g in legs) for legs in slots])
        p(f"\n=== {name}: {sum(len(x) for x in slots)} trades, {r.mean():+.3f}R per slot, "
          f"Sharpe {L.sharpe(r, 69.8):.2f}")
        for risk in (0.05, 0.06, 0.07, 0.08, 0.10):
            cells = []
            for lab, since in (("2016-26", "2016-01-01"), ("2025-26", "2025-01-01"), ("2026", "2026-01-01")):
                m = (S.gotobi >= since).values
                b, dd, n, halt, _ = replay([s for s, k in zip(slots, m) if k], S.gotobi[m], risk)
                cells.append(f"{lab} ${b:>9,.0f} DD{dd:4.0%}" + (f" HALT {halt.date()}" if halt is not None else ""))
            med, ploss, p30, p50, mdd = mc(r, risk)
            hmed, hploss, _, hp50, _ = mc(r, risk, shift=r.mean() / 2)
            p(f"  {risk:4.0%} | " + " | ".join(cells))
            p(f"        3-year Monte Carlo: median x{med:.2f}, P(loss) {ploss:4.0%}, P(DD>30%) {p30:4.0%}, "
              f"P(DD>50%) {p50:4.1%}, median DD {mdd:4.0%} | half the edge: median x{hmed:.2f}, P(loss) {hploss:4.0%}, "
              f"P(DD>50%) {hp50:4.1%}")
    (L.RES / f"lab3_report_haircut{haircut:g}.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 0.0)
