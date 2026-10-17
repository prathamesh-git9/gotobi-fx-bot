"""Gold Asia Night with a fixed kill switch, EUR 100, 2016-2026 in order (no reshuffling).

Kill switch (set before looking, not tuned): every signal is tracked, but real money is used only when
the last 30 signals had a win rate >= 60% AND a positive total R. Otherwise the trade is paper only.
Irish CGT (33% above EUR 1,270 a year) is settled each 31 December.
"""
import numpy as np
import pandas as pd

w = pd.read_parquet("../results/asia_night_trades.parquet").sort_values("day")
EURUSD, CGT, EXEMPT = 1.17, 0.33, 1270.0


def run(col, risk, switch=True, start=100.0):
    r = w[col].to_numpy()
    years = w.day.dt.year.to_numpy()
    bal, peak, dd, ypnl, live_n = start, start, 0.0, 0.0, 0
    by_year = {}
    for i in range(len(r)):
        hist = r[max(0, i - 30):i]
        live = (not switch) or (len(hist) == 30 and (hist > 0).mean() >= 0.60 and hist.sum() > 0)
        if live:
            pnl = bal * risk * r[i]
            bal += pnl
            ypnl += pnl
            live_n += 1
            peak = max(peak, bal)
            dd = max(dd, 1 - bal / peak)
        if i == len(r) - 1 or years[i + 1] != years[i]:
            tax = CGT * max(0.0, ypnl - EXEMPT) if ypnl > 0 else 0.0
            bal -= tax
            by_year[int(years[i])] = round(bal)
            ypnl = 0.0
    return bal, dd, live_n, by_year


for col, label in (("r_actual", "real spreads of each year"), ("r_modern", "today's spread in every year")):
    print(f"\n### {label}")
    for risk in (0.05, 0.10):
        for sw in (False, True):
            bal, dd, n, by = run(col, risk, sw)
            print(f"risk {risk:.0%} {'WITH kill switch' if sw else 'no kill switch  '}: EUR 100 -> EUR {bal:,.0f}  "
                  f"maxDD {dd:.0%}  live trades {n}/{len(w)}")
            print("     year-end balance:", by)
    for start in ("2023-10-01",):
        sub = w[w.day >= start]
for risk in (0.05, 0.10):
    r = w[w.day >= "2023-10-01"]["r_actual"].to_numpy()
    bal = 100.0
    peak, dd = bal, 0
    for x in r:
        bal *= 1 + risk * x
        peak = max(peak, bal); dd = max(dd, 1 - bal / peak)
    print(f"\nLast 3 years only (Oct 2023-Sep 2026), real costs, risk {risk:.0%}: EUR 100 -> EUR {bal:,.0f}, maxDD {dd:.0%}")
