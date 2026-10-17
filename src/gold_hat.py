"""Gold's 'hat-shaped' day: up in Asian hours, down in Western hours?

Independent descriptions of the effect (not found by searching our own data):
  Donati & Jung, "Gold price dynamics around the clock" (CBS thesis): gold appreciates robustly during
    eastern trading hours and depreciates for the rest of the day.
  World Gold Council session breakdown, H1 2026: Asian hours +12.9%, North American hours -15%.
Proposed cause: physical demand from China/India priced in their hours; Western selling/hedging in US hours.

Fixed sessions (natural market boundaries, chosen before looking at results here):
  ASIA  long  18:05 -> 03:00 New York   (after the daily reopen spike, out at the London open)
  US    short 08:00 -> 16:55 New York   (New York open to just before the 17:00 rollover)
Both are flat across the rollover, so no financing. Fills at the real Exness Standard bid/ask
(+0.2 bp slippage per side); 'modern' replaces the historical spread with today's (0.6 bp round trip).
"""
import numpy as np
import pandas as pd

from high_wr import RES, load_gold

SLIP = 0.2e-4
MODERN_RT = 0.6e-4


def leg(df, ny_naive, start, end, side, next_day):
    """returns per NY date for one session; start/end as minutes after midnight NY."""
    t = df.index.values
    bo, ao, bc, ac = (df[c].to_numpy() for c in ("bo", "ao", "bc", "ac"))
    dates = pd.DatetimeIndex(pd.Series(ny_naive.normalize()).unique())
    dates = dates[dates.weekday < 5] if not next_day else dates[dates.weekday.isin([0, 1, 2, 3, 6])]
    T0 = dates + pd.Timedelta(minutes=start)
    T1 = dates + pd.Timedelta(days=1 if next_day else 0, minutes=end)
    ny_v = ny_naive.values
    i0 = np.searchsorted(ny_v, T0.values, side="left")
    i1 = np.searchsorted(ny_v, T1.values, side="left") - 1
    ok = (i0 < len(t)) & (i1 > 0)
    i0, i1 = np.clip(i0, 0, len(t) - 1), np.clip(i1, 0, len(t) - 1)
    ok &= (ny_v[i0] - T0.values <= np.timedelta64(5, "m")) & (T1.values - ny_v[i1] <= np.timedelta64(5, "m")) & (i1 > i0)
    m0 = (bo[i0] + ao[i0]) / 2
    m1 = (bc[i1] + ac[i1]) / 2
    gross = side * (m1 / m0 - 1)
    if side > 0:
        net = bc[i1] / ao[i0] - 1
    else:
        net = 1 - ac[i1] / bo[i0]
    net = net - 2 * SLIP
    modern = gross - MODERN_RT - 2 * SLIP
    out = pd.DataFrame({"gross": gross, "net": net, "modern": modern,
                        "spread": (ao[i0] - bo[i0]) / m0}, index=dates)
    # key the night by the trading day it runs into (Sunday-evening -> Monday)
    if next_day:
        out.index = out.index + pd.Timedelta(days=1)
    return out[ok]


def tstat(r):
    return r.mean() / r.std() * np.sqrt(len(r))


if __name__ == "__main__":
    df = load_gold()
    ny = df.index.tz_localize("UTC").tz_convert("America/New_York").tz_localize(None)
    asia = leg(df, ny, 18 * 60 + 5, 3 * 60, +1, True)
    us = leg(df, ny, 8 * 60, 16 * 60 + 55, -1, False)
    both = asia.add(us, fill_value=0.0).dropna()
    both = both[(both.index.isin(asia.index)) & (both.index.isin(us.index))]
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    for name, x in (("ASIA long 18:05-03:00", asia), ("US short 08:00-16:55", us), ("BOTH (one long + one short a day)", both)):
        p(f"\n=== {name}: {len(x)} days {x.index.min().date()} -> {x.index.max().date()}")
        for col in ("gross", "net", "modern"):
            r = x[col]
            p(f"  {col:6s}: {r.mean() * 1e4:+.2f} bp/day  t {tstat(r):+.2f}  hit {(r > 0).mean():.1%}  "
              f"Sharpe {r.mean() / r.std() * np.sqrt(252):+.2f}  ann. return {r.mean() * 252:+.1%} (unlevered, simple)")
        g = x.groupby(x.index.year)
        tab = pd.DataFrame({"gross bp": g.gross.mean() * 1e4, "net bp": g.net.mean() * 1e4,
                            "modern bp": g.modern.mean() * 1e4, "t gross": g.gross.apply(tstat), "n": g.size()})
        p(tab.round(2).to_string())
        p(f"  years with gross > 0: {(tab['gross bp'] > 0).sum()}/{len(tab)}  | net > 0: {(tab['net bp'] > 0).sum()}/{len(tab)}"
          f"  | modern > 0: {(tab['modern bp'] > 0).sum()}/{len(tab)}")
        for lab, a, b in (("2015-2019", "2015", "2020"), ("2020-2022", "2020", "2023"), ("2023-2026", "2023", "2027")):
            s = x[(x.index >= a) & (x.index < b)]
            p(f"  {lab}: gross {s.gross.mean() * 1e4:+.2f} (t {tstat(s.gross):+.2f}) net {s.net.mean() * 1e4:+.2f} "
              f"(t {tstat(s.net):+.2f}) modern {s.modern.mean() * 1e4:+.2f} (t {tstat(s.modern):+.2f})")
    # is it just gold's trend? compare each leg with gold's same-day close-to-close move
    p("\nGold's own trend vs the legs (gross bp/day):")
    day_ret = asia.gross - us.gross.reindex(asia.index).fillna(0)
    yr = pd.DataFrame({"asia long": asia.gross.groupby(asia.index.year).mean() * 1e4,
                       "us session (as long)": -us.gross.groupby(us.index.year).mean() * 1e4})
    p(yr.round(2).to_string())
    pd.concat({"asia": asia, "us": us, "both": both}, axis=1).to_parquet(RES / "gold_hat_days.parquet")
    (RES / "gold_hat_report.txt").write_text("\n".join(lines), encoding="utf-8")
