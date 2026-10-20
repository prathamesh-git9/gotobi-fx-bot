"""NASDAQ noise-area momentum (round 6, lab6 B2 at today's spread) on a Funded Friday $10K Instant account.

Same rules and assumptions as prop_sim.py. Funded Friday requires a stop-loss on every trade and closes the account if
a floating loss passes 1% ($100), so every position gets a stop at a $90 floating loss (filled $2 worse). Position
size = the paper's leverage (2% daily-volatility target, at most 4x) times a "virtual capital" C: C = $1,100 is the
"use about EUR 1,000 of the account" plan. NASDAQ data start in Aug 2019, so the long window is 7 years, not 10.

  python strategies/prop_fundedfriday/prop_nasdaq.py
"""
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "strategies" / "breakouts"))
import lab6  # noqa: E402
import lab6_today_cost  # noqa: E402,F401  (today's NASDAQ spread)
from prop_sim import simulate  # noqa: E402

NY = ZoneInfo("America/New_York")
HALF_SPREAD = 0.85e-4 / 2
STOP_USD, SLIP_USD = 90.0, 2.0


def paths_for(positions, capital):
    out = []
    for d, side, lev, entry, exit_px, path, t_in in positions:
        n = lev * capital                                           # notional in USD
        start = pd.Timestamp(d).tz_localize(NY) + pd.Timedelta(minutes=570 + t_in)
        ts = (start + pd.to_timedelta(np.arange(len(path)), unit="min")).tz_convert(None).to_numpy()
        fl = side * (path - entry) / entry * n - n * HALF_SPREAD    # floating P&L each minute (USD)
        hit = np.nonzero(fl <= -STOP_USD)[0]
        if hit.size:
            k = hit[0]
            ts, fl = ts[:k + 1], np.r_[fl[:k], -STOP_USD - SLIP_USD]
            final = -STOP_USD - SLIP_USD
        else:
            final = side * (exit_px - entry) / entry * n
        if len(ts) == 0:
            continue
        out.append((ts, fl, fl, fl, final, pd.Timestamp(ts[-1])))
    return out


def main():
    _, _, positions = lab6.b2_daily("USTECm", positions=True)
    print(f"{len(positions)} NASDAQ momentum positions, Sep 2019 - Sep 2026")
    windows = {"since Sep 2019 (7 yrs)": (pd.Timestamp("2019-09-01"), pd.Timestamp("2026-10-01")),
               "last 2 years": (pd.Timestamp("2024-10-01"), pd.Timestamp("2026-10-01"))}
    rows = []
    for cap in (1_100, 2_500, 5_000, 10_000):
        paths = paths_for(positions, cap)
        stops = sum(1 for p in paths if p[4] <= -STOP_USD)
        for wname, (a, b) in windows.items():
            s, log = simulate(paths, 1.0, a, b, label=f"NASDAQ momentum C=${cap:,}, {wname}")
            s.update(capital=cap, window=wname, stops_hit=stops)
            rows.append(s)
            print(f"  C=${cap:>6,} {wname:22}: accounts {s['accounts']:2} (breached {s['breaches']:2}), payouts "
                  f"{s['payouts']:2} = ${s['paid']:>6,}  fees ${s['fees']:>5,}  NET ${s['net']:>+7,}  | unpaid ${s['open_profit_not_paid']:>+6,}"
                  f" | days to 1st payout {s['first_payout_days']} | $90 stops hit {stops}")
        starts = pd.date_range("2019-10-01", "2024-10-01", freq="MS")
        nets = np.array([simulate(paths, 1.0, st, st + pd.DateOffset(years=2))[0]["net"] for st in starts])
        rows.append(dict(label="rolling 2-year windows", capital=cap, windows=len(nets), median_net=float(np.median(nets)),
                         p_loss=float((nets < 0).mean()), worst=float(nets.min()), best=float(nets.max())))
        print(f"  C=${cap:>6,} every 2-year window from each month Oct 2019..Oct 2024: median NET ${np.median(nets):>+7,.0f}, "
              f"lose money in {(nets < 0).mean():4.0%} of {len(nets)}, worst ${nets.min():>+7,.0f}, best ${nets.max():>+7,.0f}")
    pd.DataFrame(rows).to_csv(HERE / "prop_nasdaq_results.csv", index=False)


if __name__ == "__main__":
    main()
