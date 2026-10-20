"""Round 8: the scalping strategies Gemini (Pro) and Qwen (3.7-Plus) proposed on 21 Oct 2026, coded exactly as they
wrote them (their answers: ai_answers.md). Where a rule needed a number they did not give, the choice is marked.

Gemini
 GM1 NY 10:00 option-cut "unpinning" fade, EURUSD: only if the 08:30-09:55 NY range is <= 15 pips (their proxy for a
     pinned market); at 10:00 NY sell if price is above the 08:00 NY open, buy if below; stop 12, target 8 pips,
     out at 10:15.
 GM2 Treasury-auction momentum, USDJPY: on 10- and 30-year auction days (US Treasury Fiscal Data, closing time
     usually 13:00 NY), if the closing-time minute's candle is > +4 pips buy (< -4 sell) at the next minute; stop 10,
     target 15, out 10 minutes after the auction.
 GM3 Friday London-close fade, GBPUSD: Fridays when the week (Monday open -> Friday 15:00 London) moved > 1.2%; at
     15:30 London fade the week; stop 15, target 20, out at 16:00 London.
 GM4 Post-NFP fade, US500: on NFP days, at 08:45 NY sell if price is in the top 10% of the 08:30-08:35 range (buy if
     in the bottom 10%); stop 15 points, target 10 points, out at 09:25.
 GM5 Shanghai open gold: buy XAUUSD at 09:29 Shanghai (01:29 UTC) if the 00:00-01:25 UTC move was "flat or slightly
     down" (my numbers: between -0.15% and +0.05%); stop $1.50, target $2.00, out at 09:45 Shanghai (01:45 UTC).
Qwen
 QW1 Month-end yen repatriation: short USDJPY at 08:30 Tokyo (23:30 UTC the evening before) on the 2nd-to-last
     Japanese business day of the month; stop max(15 pips, 1.5 x the 10-day average 1-minute range); target 10; out
     at 00:15 UTC.
 QW2 LBMA gold AM fix unwind: at 10:32 London fade the 10:30 -> 10:32 move; stop $0.60 beyond that move's high/low;
     target $1.00; out at 10:40 London.
 QW3 Friday S&P gamma pin: Fridays when US500 is within 0.15% of a 100-point strike at 13:00 NY; at 14:00 trade back
     toward that strike (short above it, long below; only if at least 0.03% away - my number); target the strike;
     stop 0.10% of price; out at 15:00 NY.
 QW4 Post-close MOC fade: if US500 moved more than 0.25% from 15:30 to 15:59 NY, fade it at 16:01 (after the bell);
     stop 0.10%, target 0.15%; out at 16:05. (Exness US index quotes stop at 15:59 on many days before 2024, so the
     sample is mostly 2023-2026.)
 QW5 Rollover "ghost wick" fade, EURUSD, Mon/Tue/Thu: if the 17:00-17:02 NY range is > 1.5x the average 1-minute range
     of 16:00-17:00, fade the longer wick at 17:02; stop 2.5 pips beyond the wick's extreme; target 3.5 pips; out at
     17:10.

Pass: positive in both halves (to 2021 / from 2022), beats the same entries in a random direction, t > 2.8.

  python strategies/scalping/lab8_ai.py
"""
import gc
import json
import sys
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "different"))
import lab4  # noqa: E402
from lab4 import M, load, nfp_days, report, run  # noqa: E402

UTC, NY, LON = ZoneInfo("UTC"), ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
lab4.PIP.update({"US500m": 0.1})
DAYS = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30")]


def mid(m, i):
    return (m.aopen[i] + m.bopen[i]) / 2


def at(d, hh, mm, tz):
    return datetime.combine(d, time(hh, mm), tz)


def GM1():
    m = M(load("EURUSDm"), 1e-4)
    p = m.pip
    sigs = []
    for d in DAYS:
        i8, i830, i955, i10, j = (m.i(at(d, 8, 0, NY)), m.i(at(d, 8, 30, NY)), m.i(at(d, 9, 55, NY)),
                                  m.i(at(d, 10, 0, NY), tol=1), m.i(at(d, 10, 15, NY)))
        if None in (i8, i830, i955, i10, j):
            continue
        hi = ((m.ahigh[i830:i955] + m.bhigh[i830:i955]) / 2).max()
        lo = ((m.alow[i830:i955] + m.blow[i830:i955]) / 2).min()
        if (hi - lo) / p > 15:
            continue
        side = -1 if mid(m, i10) > mid(m, i8) else +1 if mid(m, i10) < mid(m, i8) else 0
        if side:
            sigs.append((i10, j, side, 12 * p, 8 * p, 0.0))
    report("GM1 EURUSD 10:00 NY option-cut fade (pinned mornings)", *run(m, sigs))


def GM2():
    m = M(load("USDJPYm"), 0.01)
    p = m.pip
    auc = pd.read_csv(HERE / "data" / "treasury_10y_30y_auctions.csv")
    sigs = []
    for r in auc.itertuples():
        d = pd.Timestamp(r.auction_date).date()
        hh, mm = pd.to_datetime(r.closing_time_comp).hour, pd.to_datetime(r.closing_time_comp).minute
        t0 = at(d, hh, mm, NY)
        i0, i1 = m.i(t0, tol=1), m.i(t0 + timedelta(minutes=1), tol=1)
        j = m.i(t0 + timedelta(minutes=10), tol=2)
        if None in (i0, i1, j) or i1 - i0 != 1:
            continue
        candle = (mid(m, i1) - mid(m, i0)) / p                       # the closing-time minute, open -> close
        side = 1 if candle > 4 else -1 if candle < -4 else 0
        if side:
            sigs.append((i1, j, side, 10 * p, 15 * p, 0.0))
    print(f"   GM2: {len(auc)} auctions, {len(sigs)} with a > 4 pip candle")
    report("GM2 USDJPY Treasury-auction momentum (10y/30y)", *run(m, sigs))


def GM3():
    m = M(load("GBPUSDm"), 1e-4)
    p = m.pip
    sigs = []
    for d in DAYS:
        if d.weekday() != 4:
            continue
        monday = d - timedelta(days=4)
        i_mon = m.i(datetime.combine(monday - timedelta(days=1), time(22, 0), UTC), tol=180)   # first quote of the week
        i15, i1530, j = m.i(at(d, 15, 0, LON)), m.i(at(d, 15, 30, LON), tol=1), m.i(at(d, 16, 0, LON))
        if None in (i_mon, i15, i1530, j):
            continue
        wk = mid(m, i15) / mid(m, i_mon) - 1
        if abs(wk) > 0.012:
            sigs.append((i1530, j, -int(np.sign(wk)), 15 * p, 20 * p, 0.0))
    report("GM3 GBPUSD Friday London-close fade of a >1.2% week", *run(m, sigs))


def GM4():
    e = M(load("EURUSDm"), 1e-4)
    days = set(nfp_days(e, 1e-4))
    del e
    gc.collect()
    m = M(load("US500m"), 0.1)
    sigs = []
    for d in sorted(days):
        i0, i5, i45, j = m.i(at(d, 8, 30, NY)), m.i(at(d, 8, 35, NY)), m.i(at(d, 8, 45, NY), tol=1), m.i(at(d, 9, 25, NY))
        if None in (i0, i5, i45, j):
            continue
        hi = ((m.ahigh[i0:i5] + m.bhigh[i0:i5]) / 2).max()
        lo = ((m.alow[i0:i5] + m.blow[i0:i5]) / 2).min()
        if hi <= lo:
            continue
        x = mid(m, i45)
        side = -1 if x >= lo + 0.9 * (hi - lo) else +1 if x <= lo + 0.1 * (hi - lo) else 0
        if side:
            sigs.append((i45, j, side, 15.0, 10.0, 0.0))
    print(f"   GM4: {len(days)} NFP days, {len(sigs)} at an extreme at 08:45")
    report("GM4 US500 post-NFP fade at 08:45", *run(m, sigs))


def GM5():
    m = M(load("XAUUSDm"), 0.1)
    sigs = []
    for d in DAYS:
        i0, i125, i129, j = (m.i(datetime.combine(d, time(0, 0), UTC), tol=10), m.i(datetime.combine(d, time(1, 25), UTC)),
                             m.i(datetime.combine(d, time(1, 29), UTC), tol=1), m.i(datetime.combine(d, time(1, 45), UTC)))
        if None in (i0, i125, i129, j):
            continue
        r = mid(m, i125) / mid(m, i0) - 1
        if -0.0015 <= r <= 0.0005:
            sigs.append((i129, j, +1, 1.50, 2.00, 0.0))
    report("GM5 XAUUSD buy into the Shanghai 09:30 (flat/down Asia)", *run(m, sigs))


def QW1():
    import holidays
    jp = holidays.Japan(years=range(2016, 2027))
    bdays = [d for d in DAYS if d not in jp]
    targets = []
    for (y, mo), g in pd.Series(bdays).groupby([pd.Series(bdays).map(lambda x: x.year), pd.Series(bdays).map(lambda x: x.month)]):
        if len(g) >= 2:
            targets.append(sorted(g)[-2])
    m = M(load("USDJPYm"), 0.01)
    p = m.pip
    rng1 = (((m.ahigh + m.bhigh) - (m.alow + m.blow)) / 2) / p              # 1-minute range in pips
    sigs = []
    for d in targets:
        t0 = datetime.combine(d - timedelta(days=1), time(23, 30), UTC)
        i, j = m.i(t0, tol=2), m.i(datetime.combine(d, time(0, 15), UTC), tol=2)
        if None in (i, j):
            continue
        stop = max(15.0, 1.5 * np.nanmean(rng1[max(0, i - 14400):i]))      # ~10 trading days of minutes
        sigs.append((i, j, -1, stop * p, 10 * p, 0.0))
    report("QW1 USDJPY month-end repatriation short, Tokyo 08:30", *run(m, sigs))


def QW2():
    m = M(load("XAUUSDm"), 0.1)
    sigs = []
    for d in DAYS:
        i0, i2, j = m.i(at(d, 10, 30, LON), tol=1), m.i(at(d, 10, 32, LON), tol=1), m.i(at(d, 10, 40, LON))
        if None in (i0, i2, j) or i2 <= i0:
            continue
        mv = mid(m, i2) - mid(m, i0)
        if mv == 0:
            continue
        side = -1 if mv > 0 else 1
        hi = ((m.ahigh[i0:i2] + m.bhigh[i0:i2]) / 2).max()
        lo = ((m.alow[i0:i2] + m.blow[i0:i2]) / 2).min()
        e = m.aopen[i2] if side > 0 else m.bopen[i2]
        stop_d = (e - (lo - 0.60)) if side > 0 else ((hi + 0.60) - e)
        if stop_d > 0:
            sigs.append((i2, j, side, stop_d, 1.00, 0.0))
    report("QW2 XAUUSD LBMA AM fix unwind fade", *run(m, sigs))


def QW3():
    m = M(load("US500m"), 0.1)
    sigs = []
    for d in DAYS:
        if d.weekday() != 4:
            continue
        i13, i14, j = m.i(at(d, 13, 0, NY), tol=2), m.i(at(d, 14, 0, NY), tol=1), m.i(at(d, 15, 0, NY))
        if None in (i13, i14, j):
            continue
        x13 = mid(m, i13)
        strike = round(x13 / 100) * 100
        if abs(x13 / strike - 1) > 0.0015:
            continue
        x = mid(m, i14)
        if abs(x / strike - 1) < 0.0003:
            continue
        side = -1 if x > strike else 1
        e = m.aopen[i14] if side > 0 else m.bopen[i14]
        tp = (strike - e) if side > 0 else (e - strike)
        if tp > 0:
            sigs.append((i14, j, side, 0.001 * e, tp, 0.0))
    report("QW3 US500 Friday gamma pin back to a 100-point strike", *run(m, sigs))


def QW4():
    m = M(load("US500m"), 0.1)
    sigs = []
    for d in DAYS:
        i30, i59, i61, j = (m.i(at(d, 15, 30, NY)), m.i(at(d, 15, 59, NY), tol=1), m.i(at(d, 16, 1, NY), tol=1),
                            m.i(at(d, 16, 5, NY), tol=1))
        if None in (i30, i59, i61, j) or i61 - i59 > 3:
            continue
        mv = mid(m, i59) / mid(m, i30) - 1
        if abs(mv) > 0.0025:
            side = -int(np.sign(mv))
            e = m.aopen[i61] if side > 0 else m.bopen[i61]
            sigs.append((i61, j, side, 0.0010 * e, 0.0015 * e, 0.0))
    report("QW4 US500 post-close MOC exhaustion fade", *run(m, sigs))


def QW5():
    m = M(load("EURUSDm"), 1e-4)
    p = m.pip
    sigs = []
    for d in DAYS:
        if d.weekday() not in (0, 1, 3):
            continue
        i16, i17, i1702, j = m.i(at(d, 16, 0, NY)), m.i(at(d, 17, 0, NY), tol=1), m.i(at(d, 17, 2, NY), tol=1), m.i(at(d, 17, 10, NY))
        if None in (i16, i17, i1702, j) or i1702 <= i17:
            continue
        avg1 = np.mean(((m.ahigh[i16:i17] + m.bhigh[i16:i17]) - (m.alow[i16:i17] + m.blow[i16:i17])) / 2)
        hi = ((m.ahigh[i17:i1702] + m.bhigh[i17:i1702]) / 2).max()
        lo = ((m.alow[i17:i1702] + m.blow[i17:i1702]) / 2).min()
        if hi - lo <= 1.5 * avg1:
            continue
        o = mid(m, i17)
        side = -1 if (hi - o) > (o - lo) else 1
        e = m.aopen[i1702] if side > 0 else m.bopen[i1702]
        stop_d = (e - (lo - 2.5 * p)) if side > 0 else ((hi + 2.5 * p) - e)
        if stop_d > 0:
            sigs.append((i1702, j, side, stop_d, 3.5 * p, 0.0))
    report("QW5 EURUSD 17:00 NY rollover ghost-wick fade", *run(m, sigs))


if __name__ == "__main__":
    for k in sys.argv[1:] or [n for n in dir() if n[:2] in ("GM", "QW") and n[2:].isdigit()]:
        globals()[k]()
        gc.collect()
    f = HERE / "lab8_ai_results.json"
    old = json.loads(f.read_text()) if f.exists() else {}
    old.update({r["name"]: r for r in lab4.OUT})
    f.write_text(json.dumps(old, indent=1, default=str))
