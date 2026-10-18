"""Second-by-second view of the 09:55 JST Tokyo fix on gotobi days (raw Exness ticks, data/fix_ticks/).

Questions minute bars cannot answer:
  1. How fast does USD/JPY drop after 09:55:00 on gotobi days? (mid move vs the last pre-fix quote)
  2. What does the post-fix short (out at fix + 30 min) earn if the order lands d seconds after 09:55:00,
     d from -10 (early) to +60? A market order fills at the quote prevailing when it arrives.
  3. When is the best moment to close the long: 00:54:00 (the bot now) or a few seconds before the fix?
  Same on non-gotobi fix days as a placebo.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import gotobi_lab as L
import gotobi_lab2 as L2

TICKS = Path(__file__).resolve().parent.parent / "data" / "fix_ticks"
SLIP = 0.2e-4
DELAYS = [-10, -5, -3, -2, -1, -0.5, 0, 0.25, 0.5, 1, 2, 3, 5, 10, 20, 30, 60]
PROFILE = [-30, -10, -5, -2, -1, 0, 0.5, 1, 2, 3, 5, 10, 20, 30, 60, 120, 300, 600, 1800]


def load_ticks() -> pd.DataFrame:
    parts = [pd.read_parquet(f) for f in sorted(TICKS.glob("USDJPYm_*.parquet"))]
    t = pd.concat(parts).sort_index()
    return t


def quote_at(ts_ns: np.ndarray, bid: np.ndarray, ask: np.ndarray, when_ns: int):
    """Quote prevailing at `when`: the last tick at or before it."""
    i = int(np.searchsorted(ts_ns, when_ns, side="right")) - 1
    return (bid[i], ask[i]) if i >= 0 else (np.nan, np.nan)


def day_rows(t: pd.DataFrame, days: pd.DatetimeIndex) -> pd.DataFrame:
    ts = t.index.values.astype("datetime64[ns]").astype(np.int64)
    bid, ask = t.bid.to_numpy(), t.ask.to_numpy()
    rows = []
    for d in days:
        fix = int((d + pd.Timedelta(minutes=55)).value)
        lo, hi = np.searchsorted(ts, [fix - 600 * 10**9, fix + 1900 * 10**9])
        if hi - lo < 50:                       # no ticks around this fix (data gap)
            continue
        b0, a0 = quote_at(ts, bid, ask, fix - 1)    # last quote before 09:55:00
        m0 = (b0 + a0) / 2
        row = {"day": d}
        for s in PROFILE:
            b, a = quote_at(ts, bid, ask, fix + int(s * 1e9))
            row[f"mv_{s}"] = ((b + a) / 2 - m0) / L.PIP
        xb, xa = quote_at(ts, bid, ask, fix + 1800 * 10**9)          # exit the short at fix + 30 min
        for dl in DELAYS:
            b, a = quote_at(ts, bid, ask, fix + int(dl * 1e9))
            ent, ex = b * (1 - SLIP), xa * (1 + SLIP)
            row[f"short_{dl}"] = (ent - ex) / L.PIP
        for s in (60, 30, 10, 5, 2, 1, 0.5, 0):                     # close the long s seconds before the fix
            b, a = quote_at(ts, bid, ask, fix - int(s * 1e9) - (1 if s == 0 else 0))
            row[f"longexit_{s}"] = b * (1 - SLIP)
        # first post-fix tick (the minute-bar 'open' the lab used)
        j = int(np.searchsorted(ts, fix, side="left"))
        row["first_tick_lag_ms"] = (ts[j] - fix) / 1e6
        row["short_firsttick"] = (bid[j] * (1 - SLIP) - xa * (1 + SLIP)) / L.PIP
        rows.append(row)
    return pd.DataFrame(rows)


def tstat(x: pd.Series) -> float:
    x = x.dropna()
    return float(x.mean() / x.std(ddof=1) * np.sqrt(len(x)))


if __name__ == "__main__":
    t = load_ticks()
    S = L.load_slots()
    g = day_rows(t, pd.DatetimeIndex(S.gotobi))
    c = day_rows(t, L2.control_days(S))
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p(f"ticks {t.index[0]} -> {t.index[-1]}: {len(t):,}; gotobi fixes with ticks {len(g)}, control fixes {len(c)}")
    p(f"first tick after 09:55:00 arrives after median {g.first_tick_lag_ms.median():.0f} ms "
      f"(90th pct {g.first_tick_lag_ms.quantile(.9):.0f} ms)")
    p("\n1) Mid move vs the last quote before 09:55:00 (pips): mean, gotobi | control")
    for s in PROFILE:
        p(f"   {s:+7.1f} s: gotobi {g[f'mv_{s}'].mean():+6.2f} (t {tstat(g[f'mv_{s}']):+5.2f}) | control {c[f'mv_{s}'].mean():+6.2f}")
    p("\n2) Post-fix short, out at 09:55 + 30 min: average pips by when the order lands (after spread + slippage)")
    for dl in DELAYS:
        x, y = g[f"short_{dl}"], c[f"short_{dl}"]
        hold = g.day >= L.SPLIT
        p(f"   {dl:+6.2f} s: gotobi {x.mean():+5.2f} pips (t {tstat(x):+5.2f}; 2016-21 {x[~hold].mean():+5.2f}, "
          f"2022-26 {x[hold].mean():+5.2f}) | control {y.mean():+5.2f} (t {tstat(y):+5.2f})")
    p(f"   first tick after the fix (the minute-bar backtest): gotobi {g.short_firsttick.mean():+5.2f} pips")
    p("\n3) Closing the long: price vs closing at 00:54:00 (pips, + = better)")
    for s in (30, 10, 5, 2, 1, 0.5, 0):
        d = (g[f"longexit_{s}"] - g["longexit_60"]) / L.PIP
        p(f"   {s:4.1f} s before the fix: {d.mean():+5.2f} pips (t {tstat(d):+5.2f})")
    g.to_parquet(L.RES / "fix_seconds_gotobi.parquet")
    (L.RES / "fix_seconds_report.txt").write_text("\n".join(lines), encoding="utf-8")
