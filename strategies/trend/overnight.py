"""The overnight anomaly on Exness index CFDs, at real bid/ask, with and without swaps.

US stocks have earned almost all their return outside trading hours (Cliff, Cooper & Gulen 2008; Kelly & Clark 2011;
Lou, Polk & Skouras 2019, "A tug of war: overnight versus intraday expected returns", JFE). This repo tested it once
(src/classics.py, daily closes, CFD financing) and it lost. Now, on Exness minute bid/ask:
 ON  buy at 15:58 New York (the ask), sell at 09:35 New York next trading day (the bid) - every day.
 ID  the opposite half: buy 09:35, sell 15:58 the same day (for comparison).
 BH  buy and hold (for comparison).
Financing: (i) zero (Exness swap-free status kept); (ii) a swap estimate: long index CFD financing = (3-month T-bill +
2.5%)/360 per night on the price, triple on Fridays (Exness books index weekends on Fridays). US500, USTEC, US30;
Aug 2019 - Sep 2026. Fixed before running.

  python strategies/trend/overnight.py
"""
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "strategies" / "different"))
from lab4 import M  # noqa: E402

NY = ZoneInfo("America/New_York")
COLS = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]


def rates():
    y = pd.read_parquet(ROOT / "data" / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    irx = y[y.sym == "^IRX"].set_index("date").close
    irx.index = pd.to_datetime(irx.index)
    return irx.sort_index()


def run(sym):
    df = pd.read_parquet(ROOT / "data" / f"{sym}_m1.parquet", columns=COLS)
    m = M(df[df.index < "2026-10-01"], 1.0)
    days = [d.date() for d in pd.bdate_range("2019-08-05", "2026-09-30")]
    irx = rates()
    rows = []
    for d0, d1 in zip(days, days[1:]):
        i_close = m.i(datetime.combine(d0, time(15, 58), NY), tol=1)
        i_open = m.i(datetime.combine(d1, time(9, 35), NY), tol=2)
        i_open0 = m.i(datetime.combine(d0, time(9, 35), NY), tol=2)
        if None in (i_close, i_open, i_open0) or (d1 - d0).days > 4:
            continue
        on = m.bopen[i_open] / m.aopen[i_close] - 1                 # buy the ask at 15:58, sell the bid at 09:35
        idr = m.bopen[i_close] / m.aopen[i_open0] - 1               # buy 09:35, sell 15:58 the same day
        mid_on = (m.bopen[i_open] + m.aopen[i_open]) / (m.bopen[i_close] + m.aopen[i_close]) - 1
        nights = 3 if d0.weekday() == 4 else (d1 - d0).days
        rate = (irx.asof(pd.Timestamp(d0)) + 2.5) / 100
        rows.append(dict(d=pd.Timestamp(d1), on=on, on_gross=mid_on, id=idr, swap=rate / 360 * nights,
                         spread_bp=((m.aopen[i_close] - m.bopen[i_close]) / m.bopen[i_close] + (m.aopen[i_open] - m.bopen[i_open]) / m.bopen[i_open]) / 2 * 1e4))
    return pd.DataFrame(rows).set_index("d")


def stats(x, a, b):
    x = x[(x.index >= a) & (x.index < b)]
    eq = 1000 * (1 + x).cumprod()
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    return (round(float(eq.iloc[-1])), round(float((eq.iloc[-1] / 1000) ** (1 / yrs) - 1) * 100, 1),
            round(float(x.mean() / x.std() * np.sqrt(252)), 2), round(float((1 - eq / eq.cummax()).max()) * 100, 1),
            round(float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))), 2))


def main():
    W = {"since Aug 2019": ("2019-08-01", "2026-10-01"), "2019-21": ("2019-08-01", "2022-01-01"), "2022-26": ("2022-01-01", "2026-10-01"),
         "last 2 yrs": ("2024-10-01", "2026-10-01"), "2026": ("2026-01-01", "2026-10-01")}
    for sym in ("US500m", "USTECm", "US30m"):
        t = run(sym)
        print(f"\n===== {sym[:-1]}: {len(t)} nights; median round-trip spread paid {t.spread_bp.median() * 2:.2f} bp "
              f"(2019-24 {t[t.index < '2024-10-01'].spread_bp.median() * 2:.2f}, since Oct 2024 {t[t.index >= '2024-10-01'].spread_bp.median() * 2:.2f})")
        series = {"OVERNIGHT, zero swap (1x)": t.on, "OVERNIGHT, with swap estimate (1x)": t.on - t.swap,
                  "overnight before costs (mid to mid)": t.on_gross, "INTRADAY 09:35-15:58 (1x)": t.id}
        for name, x in series.items():
            print(f"  {name}")
            for wn, (a, b) in W.items():
                eur, cagr, sh, dd, tt = stats(x, a, b)
                print(f"     {wn:15}: EUR 1,000 -> {eur:>6,} ({cagr:+5.1f}%/yr, Sharpe {sh:+.2f}, t {tt:+.2f}, max drop {dd:4.1f}%)")


if __name__ == "__main__":
    main()
