"""Instant Funding PRO $5K with NO withdrawals: risk 8% of a 'virtual' capital V per trade (fixed, or growing with
the profit), never above the firm's 3% cap ($150). Same minute-by-minute rules as prop_multi.py (10% static floor,
fixed at -5% once +5%; breach checked on the worst price of every minute).

  python strategies/prop_firms/no_payout_2026.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "prop_fundedfriday"))
from prop_sim import trade_paths, usdjpy  # noqa: E402

SIZE, CAP = 5000.0, 150.0


def run(paths, v, start, end, grow):
    bal, locked, peak, low, n = SIZE, False, SIZE, SIZE, 0
    for ts, worst, best, close, r, closed in paths:
        if not (start <= closed < end):
            continue
        risk = min(CAP, 0.08 * (v + (bal - SIZE) if grow else v))
        floor = SIZE * (0.95 if locked else 0.90)
        if ((bal + worst * risk) < floor).any():
            return dict(breached=closed, final=None, peak=peak, low=low, trades=n)
        bal += r * risk
        n += 1
        peak, low = max(peak, bal), min(low, bal)
        locked = locked or bal >= SIZE * 1.05
    return dict(breached=None, final=bal, peak=peak, low=low, trades=n)


def main():
    t = pd.read_csv(ROOT / "strategies" / "edge7" / "gotobi_bot_trades_2016_2026.csv")
    t["closed_ts"] = pd.to_datetime(t.closed, utc=True).dt.tz_convert(None)
    paths = trade_paths(t.sort_values("closed_ts"), usdjpy())
    a, b = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-10-21")
    starts = pd.date_range("2016-11-01", "2025-10-01", freq="MS")
    print("Instant Funding PRO $5K, no payouts, 8% of virtual capital V per trade (cap $150)\n")
    for grow in (False, True):
        print(("FIXED risk = 8% of V" if not grow else "GROWING risk = 8% of (V + profit so far), capped at $150"))
        for v in (500, 750, 1000, 1250, 1500, 1875):
            s = run(paths, v, a, b, grow)
            hist = [run(paths, v, st, st + pd.DateOffset(years=1), grow) for st in starts]
            p_b = np.mean([h["breached"] is not None for h in hist])
            res = (f"breached {s['breached']:%d %b}" if s["breached"] is not None else
                   f"balance today ${s['final']:,.0f} (profit ${s['final'] - SIZE:+,.0f}; you'd get 80% = ${0.8 * (s['final'] - SIZE):+,.0f})")
            print(f"  V=${v:>5,} (~EUR {v / 1.16:>5,.0f}) -> ${min(CAP, 0.08 * v):>4.0f}/trade at the start | 2026: {res}, "
                  f"highest ${s['peak']:,.0f}, lowest ${s['low']:,.0f} | lost within 12 months in {p_b:4.0%} of 108 past start months")
        print()


if __name__ == "__main__":
    main()
