"""What the Gotobi rule could do for EUR 100: Kelly, Monte Carlo, the real 2016-2026 sequence, leverage limits.

Trades: window A (the pasted rule), net of real Exness bid/ask + slippage, swap excluded (bonus if positive).
1R = the 55-pip catastrophic stop. Optional add-on D: reverse to short at the 09:55 fix, out at 11:00 JST.
Scenarios: 'history' = bootstrap the 2016-2026 trades; 'half edge' = same trades minus half their mean
(live trading usually falls short of a backtest).
"""
import numpy as np
import pandas as pd

import gotobi as G

RNG = np.random.default_rng(11)
CGT, EXEMPT, EURUSD = 0.33, 1270.0, 1.17
RISKS = [0.01, 0.02, 0.031, 0.05, 0.10]


def chrono(day, r, risk, start=100.0):
    bal, peak, dd, year, ypnl = start, start, 0.0, None, 0.0
    for d, x in zip(day, r):
        if year is not None and d.year != year:
            bal -= CGT * max(0.0, ypnl - EXEMPT) if ypnl > 0 else 0.0
            ypnl = 0.0
        year = d.year
        pnl = bal * risk * x
        bal += pnl
        ypnl += pnl
        peak = max(peak, bal)
        dd = max(dd, 1 - bal / peak)
    bal -= CGT * max(0.0, ypnl - EXEMPT) if ypnl > 0 else 0.0
    return bal, dd


if __name__ == "__main__":
    df = G.load()
    start, end = df.index[0].normalize() + pd.Timedelta(days=2), df.index[-1].normalize() - pd.Timedelta(days=1)
    diff = G.rate_series(start - pd.Timedelta(days=5), end + pd.Timedelta(days=5)).to_dict()
    for jp in (False, True):
        days = G.gotobi_dates(start, end, jp)
        a = G.trades(df, days, "A", diff).set_index("day")
        d = G.trades(df, days, "D", diff).set_index("day")
        both = (a.net + d.net.reindex(a.index).fillna(0)) / 2      # same total risk split over two trades
        books = {"A only (pasted rule)": a.net / G.STOP_PIPS, "A + D (long into fix, short after)": both / G.STOP_PIPS}
        print(f"\n################ {'Japanese holidays moved' if jp else 'pasted rule dates'}")
        for name, r in books.items():
            r = r.dropna()
            per_year = len(r) / ((r.index[-1] - r.index[0]).days / 365.25)
            fs = np.linspace(0, 0.6, 601)
            kelly = fs[int(np.argmax([np.mean(np.log1p(f * r)) if (1 + f * r).min() > 0 else -np.inf for f in fs]))]
            print(f"\n=== {name}: {len(r)} trades ({per_year:.0f}/yr)  avg {r.mean():+.3f}R  win {np.mean(r > 0):.1%}  "
                  f"full-Kelly risk {kelly:.0%} per trade")
            for lab, x in (("history", r.to_numpy()), ("half edge", (r - r.mean() / 2).to_numpy())):
                print(f"  -- scenario: {lab} (avg {x.mean():+.3f}R)")
                n3 = int(per_year * 3)
                for risk in RISKS:
                    paths = 100 * np.cumprod(1 + risk * RNG.choice(x, (20000, n3)), axis=1)
                    end_ = paths[:, -1]
                    dd = (1 - paths / np.maximum.accumulate(paths, axis=1)).max(1)
                    print(f"     risk {risk:5.1%}: 3-year EUR 100 -> median {np.median(end_):6,.0f} "
                          f"(5%: {np.percentile(end_, 5):5,.0f}, 95%: {np.percentile(end_, 95):7,.0f})  P(loss) {np.mean(end_ < 100):4.0%}  "
                          f"median maxDD {np.median(dd):4.0%}  P(DD>50%) {np.mean(dd > 0.5):4.0%}")
            print("  -- real sequence (with Irish CGT):")
            for risk in (0.02, 0.05, 0.10):
                b, dd = chrono(r.index, r.to_numpy(), risk)
                b3, dd3 = chrono(r[r.index >= "2023-10-01"].index, r[r.index >= "2023-10-01"].to_numpy(), risk)
                b18, dd18 = chrono(r[r.index < "2019-01-01"].index, r[r.index < "2019-01-01"].to_numpy(), risk)
                print(f"     risk {risk:4.0%}: 2016-2026 EUR 100 -> {b:9,.0f} (max DD {dd:.0%}) | 2016-18 only -> {b18:5,.0f} "
                      f"(DD {dd18:.0%}) | last 3 years -> {b3:6,.0f} (DD {dd3:.0%})")
    px = df.bopen.iloc[-1]
    stop_frac = G.STOP_PIPS / 100 / px
    print(f"\nLeverage at USD/JPY {px:.1f}: a 55-pip stop = {stop_frac:.3%} of the position")
    for risk in (0.01, 0.02, 0.05, 0.10):
        lev = risk / stop_frac
        print(f"  risk {risk:4.0%} -> position = {lev:4.1f}x equity = {100 * EURUSD * lev:,.0f} USD on EUR 100 "
              f"({100 * EURUSD * lev / 100000:.4f} standard lots)  {'OK' if lev <= 30 else 'ABOVE'} the EU 30:1 cap")
    print(f"  Exness Standard minimum 0.01 lot = 1,000 USD -> min risk {1000 * stop_frac / (100 * EURUSD):.1%} of EUR 100; "
          f"the Standard Cent account (same USD/JPY spread, checked) can size 1% exactly.")
