"""Round 3 (my half; Codex invents its own in codex_audit/explore3). Rules fixed before running; same pass rule as
lab.py (both halves positive, beats ordinary days, t > 2).

 H. Japanese importers pay ahead of long Tokyo closures: on the last Tokyo business day before a closure of 4+
    calendar days (Golden Week, year-end, Silver Week, 3-day weekends), NOT a gotobi day, run the gotobi long
    (buy 15:55 UTC day before, stop 55, TP 30, sell 00:54 UTC). USDJPY and EURJPY, 2016-26, plus USDJPY 2006-15.
 I. US corporate estimated-tax days (15 Apr/Jun/Sep/Dec, moved to the next business day): companies raise dollars.
    Buy USD 08:00 -> 16:00 London on the tax day (EURUSD short, USDJPY long, GBPUSD short).
 J. Weekly Friday 4 pm fix: buy GBPUSD / EURUSD 15:45 -> 16:00 London on Fridays that are not month-ends.
 K. Mid-month 4 pm fix: buy GBPUSD 15:45 -> 16:00 London on the business day nearest the 15th.
 L. Month-end GBP: quarter-ends vs other month-ends (a description, not a new rule).
 M. Sterling at the month-end fix through the crosses: sell EURGBP, buy GBPJPY 15:45 -> 16:00 London (if a sterling
    buyer drives the GBPUSD effect, both should work).
 N. Gotobi long on GBPJPY, CADJPY, CHFJPY.

  python strategies/explore/lab3.py [H I J ...]
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402
from lab import COLS, LON, ROOT, UTC, GotobiCalendar, XPx, at, judge, month_end_days, tp_trade  # noqa: E402

import holidays  # noqa: E402

lab.PIP.update({"EURGBPm": 1e-4, "GBPJPYm": 0.01, "CADJPYm": 0.01, "CHFJPYm": 0.01})
UK = holidays.UK(years=range(2006, 2027))
ME = month_end_days(date(2006, 1, 1), date(2026, 9, 30), UK)
LDAYS = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30") if d.date() not in UK]


def gotobi_long(px, d):
    prev = d - timedelta(days=3 if d.weekday() == 0 else 1)
    e0 = datetime.combine(prev, time(15, 55), UTC) if d.weekday() else datetime.combine(d - timedelta(days=1), time(22, 15), UTC)
    return tp_trade(px, e0, datetime.combine(d, time(0, 54), UTC), +1, 55, 30)


def H():
    print("\nH. Last Tokyo business day before a 4+ day closure (not a gotobi day), gotobi-style long")
    cal = GotobiCalendar()
    for start, end, syms in ((date(2016, 1, 1), date(2026, 9, 30), ("USDJPYm", "EURJPYm")), (date(2006, 1, 1), date(2015, 12, 31), ("USDJPY 2006-15",))):
        bdays = [d.date() for d in pd.date_range(start, end + timedelta(days=10)) if cal.business_day(d.date())]
        got = set(cal.trade_days(start, end))
        ev = {a for a, b in zip(bdays, bdays[1:]) if (b - a).days >= 4 and a not in got and a <= end}
        days = [d for d in bdays if d not in got and d <= end]
        for sym in syms:
            if sym.startswith("USDJPY 2006"):
                from cross_oos import Bars
                px = Bars(pd.read_parquet(ROOT / "data/histdata/USDJPY_hd_model_2006_2015_m1.parquet", columns=COLS), 0.01)
            else:
                px = XPx(sym)
            judge(f"{sym} pre-closure long ({len(ev)} events)", [(d, gotobi_long(px, d), d in ev) for d in days],
                  split=2021 if start.year == 2016 else 2010)


def tax_days():
    us = holidays.US(years=range(2016, 2027))
    out = set()
    for y in range(2016, 2027):
        for m in (4, 6, 9, 12):
            d = date(y, m, 15)
            while d.weekday() >= 5 or d in us:
                d += timedelta(days=1)
            out.add(d)
    return out


def I():
    print("\nI. US corporate tax days: buy USD 08:00 -> 16:00 London")
    tax = tax_days()
    for sym, side, stop in (("EURUSDm", -1, 50), ("GBPUSDm", -1, 60), ("USDJPYm", +1, 60)):
        px = XPx(sym)
        judge(f"{'sell' if side < 0 else 'buy'} {sym} on tax days", [(d, px.trade(at(d, "08:00", LON), at(d, "16:00", LON), side, stop), d in tax) for d in LDAYS])


def fix_trade(px, d, side=+1, stop=25):
    return px.trade(at(d, "15:45", LON), at(d, "16:00", LON), side, stop)


def J():
    print("\nJ. Friday 4 pm fix (not month-ends), buy 15:45 -> 16:00 London")
    for sym in ("GBPUSDm", "EURUSDm"):
        px = XPx(sym)
        judge(f"buy {sym} into the Friday fix", [(d, fix_trade(px, d), d.weekday() == 4) for d in LDAYS if d not in ME])


def K():
    print("\nK. Mid-month 4 pm fix, buy GBPUSD 15:45 -> 16:00 London on the business day nearest the 15th")
    mid = set()
    for y in range(2016, 2027):
        for m in range(1, 13):
            t = date(y, m, 15)
            mid.add(min((d for d in LDAYS if abs((d - t).days) <= 3), key=lambda d: (abs((d - t).days), d), default=t))
    px = XPx("GBPUSDm")
    judge("buy GBPUSD into the mid-month fix", [(d, fix_trade(px, d), d in mid) for d in LDAYS if d not in ME])


def L():
    print("\nL. GBPUSD month-end fix: quarter-ends vs other month-ends (description)")
    px = XPx("GBPUSDm")
    rows = [(d, fix_trade(px, d), d.month in (3, 6, 9, 12)) for d in LDAYS if d in ME]
    df = pd.DataFrame(rows, columns=["d", "p", "q"]).dropna()
    print(df.groupby("q").p.agg(["count", "mean"]).rename(index={True: "quarter-end", False: "other month-end"}).round(2))


def M():
    print("\nM. Sterling through the crosses at the month-end fix (15:45 -> 16:00 London, stop 25)")
    for sym, side in (("EURGBPm", -1), ("GBPJPYm", +1)):
        try:
            px = XPx(sym)
        except FileNotFoundError:
            print(f"  {sym}: not downloaded yet")
            continue
        judge(f"{'sell' if side < 0 else 'buy'} {sym} into the month-end fix", [(d, fix_trade(px, d, side), d in ME) for d in LDAYS])


def N():
    print("\nN. Gotobi long on more yen crosses")
    got = set(GotobiCalendar().trade_days(date(2016, 1, 1), date(2026, 9, 30)))
    days = lab.tokyo_days()
    for sym in ("GBPJPYm", "CADJPYm", "CHFJPYm"):
        try:
            px = XPx(sym)
        except FileNotFoundError:
            print(f"  {sym}: not downloaded yet")
            continue
        judge(f"{sym} gotobi long", [(d, gotobi_long(px, d), d in got) for d in days])


if __name__ == "__main__":
    for k in sys.argv[1:] or "HIJKLMN":
        globals()[k]()
