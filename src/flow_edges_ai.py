"""The candidates Gemini and Qwen proposed (asked 19 Oct 2026), tested exactly as they wrote them, on the same
data, costs and split as src/flow_edges.py. EUR/GBP is left out: there is no EUR/GBP bid/ask data here.

  python src/flow_edges_ai.py
"""
import sys
from datetime import date
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from flow_edges import LON, NY, Px, at, month_end_days, summary, yahoo  # noqa: E402

UTC = ZoneInfo("UTC")


def main():
    import holidays
    uk = holidays.UK(years=range(2016, 2027))
    us = holidays.NYSE(years=range(2016, 2027))
    Y = yahoo()
    spx = Y["^GSPC"]
    px = {s: Px(s) for s in ("EURUSDm", "GBPUSDm", "XAUUSDm", "US500m")}
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30")]
    me = month_end_days(date(2016, 1, 1), date(2026, 9, 30), uk)
    res = {}

    def mtd(d):
        hist = Y.index[Y.index < pd.Timestamp(d)]
        ms = Y.index[Y.index < pd.Timestamp(d.replace(day=1))]
        return spx[hist[-1]] / spx[ms[-1]] - 1

    print("GEMINI")
    rows = []
    for d in days:
        if d in uk:
            continue
        m = mtd(d)
        if abs(m) <= 0.015:
            continue
        rows.append((d, px["EURUSDm"].trade(at(d, "15:30", LON), at(d, "16:05", LON), +1 if m > 0 else -1, 25), d in me))
    res["G1"] = summary("1 month-end fix, S&P MTD >+1.5% buy EURUSD", rows)
    qe = {d for d in me if d.month in (3, 6, 9, 12)}
    rows2 = [(d, p, d in qe) for d, p, e in rows]
    summary("  quarter-ends only", rows2)

    rows = []
    for d in days:
        if d in us or d < date(2019, 9, 1):
            continue
        prev = px["US500m"].mid(at(d - pd.Timedelta(days=1 if d.weekday() else 3), "16:00", NY))
        op = px["US500m"].mid(at(d, "09:30", NY))
        if prev is None or op is None or abs(op / prev - 1) <= 0.004:
            continue
        side = 1 if op > prev else -1
        rows.append((d, px["US500m"].trade(at(d, "09:31", NY), at(d, "09:45", NY), side, 150), True))
    res["G2"] = summary("2 US500 open gap >0.4%, go with it 09:31-09:45 NY", rows)

    rows = []
    for d in days:
        if d.weekday() not in (1, 2, 3):
            continue
        t0 = pd.Timestamp(d).tz_localize(UTC)
        a, b = px["GBPUSDm"].mid((t0 + pd.Timedelta("12:45:00")).to_pydatetime()), px["GBPUSDm"].mid((t0 + pd.Timedelta("13:15:00")).to_pydatetime())
        if a is None or b is None or abs(b - a) / 1e-4 <= 35:
            continue
        rows.append((d, px["GBPUSDm"].trade((t0 + pd.Timedelta("13:15:00")).to_pydatetime(),
                                             (t0 + pd.Timedelta("13:45:00")).to_pydatetime(), -1 if b > a else 1, 20), True))
    res["G3"] = summary("3 GBPUSD 35-pip spike 12:45-13:15 UTC, fade", rows)

    rows = []
    for d in days:
        t0 = pd.Timestamp(d).tz_localize(UTC)
        a, b = px["XAUUSDm"].mid((t0 + pd.Timedelta("08:00:00")).to_pydatetime()), px["XAUUSDm"].mid((t0 + pd.Timedelta("13:20:00")).to_pydatetime())
        if a is None or b is None or a == b:
            continue
        rows.append((d, px["XAUUSDm"].trade((t0 + pd.Timedelta("13:20:00")).to_pydatetime(),
                                             (t0 + pd.Timedelta("14:00:00")).to_pydatetime(), 1 if b > a else -1, 35), True))
    res["G5"] = summary("5 gold 13:20-14:00 UTC with the London trend", rows)
    print("\nQWEN")
    px["USDJPYm"], px["DE30m"] = Px("USDJPYm"), Px("DE30m")
    rows = []
    for d in days:
        if d in uk:
            continue
        hist = Y.index[Y.index < pd.Timestamp(d)]
        ms = Y.index[Y.index < pd.Timestamp(d.replace(day=1))]
        p, b = hist[-1], ms[-1]
        us_eur = (Y["^GSPC"][p] / Y["EURUSD=X"][p]) / (Y["^GSPC"][b] / Y["EURUSD=X"][b]) - 1
        dax = Y["^GDAXI"][p] / Y["^GDAXI"][b] - 1
        t0 = pd.Timestamp(d).tz_localize(UTC)
        rows.append((d, px["EURUSDm"].trade((t0 + pd.Timedelta("15:30:00")).to_pydatetime(),
                                             (t0 + pd.Timedelta("15:55:00")).to_pydatetime(), -1 if us_eur > dax else 1, 15), d in me))
    res["Q1"] = summary("1 month-end EURUSD 15:30-15:55 UTC, as written", rows)

    rows, per_year = [], {}
    for d in days:
        t0 = pd.Timestamp(d).tz_localize(UTC)
        p = px["USDJPYm"].trade((t0 + pd.Timedelta("00:00:00")).to_pydatetime(), (t0 + pd.Timedelta("23:55:00")).to_pydatetime(), -1, 100)
        ev = d.month == 3 and 10 <= d.day <= 28
        rows.append((d, p, ev))
        if ev and p is not None:
            per_year[d.year] = per_year.get(d.year, 0) + p
    res["Q2"] = summary("2 short USDJPY every day 10-28 March", rows)
    print("     per year (pips):", {y: round(v) for y, v in sorted(per_year.items())})

    # 3: turn of the month, long US500 from the 2nd-to-last to the 3rd trading day (16:00 NY closes), with
    # CFD financing of 6% a year on the position (Exness index swaps are of that order)
    tdays = [d for d in days if d not in us and d >= date(2019, 9, 1)]
    by_month = {}
    for d in tdays:
        by_month.setdefault((d.year, d.month), []).append(d)
    months = sorted(by_month)
    rows = []
    for a, b in zip(months, months[1:]):
        if len(by_month[a]) < 2 or len(by_month[b]) < 3:
            continue
        d0, d1 = by_month[a][-2], by_month[b][2]
        e = px["US500m"].idx(at(d0, "15:59", NY))
        x = px["US500m"].idx(at(d1, "15:59", NY))
        if e is None or x is None:
            continue
        entry, exit_ = px["US500m"].aopen[e], px["US500m"].bopen[x]
        fin = entry * 0.06 * (d1 - d0).days / 365
        rows.append((d0, (exit_ - entry - fin) / 0.1, True))
    res["Q3"] = summary("3 turn of month, long US500 (after financing)", rows)

    if px["DE30m"] is not None:
        CET = ZoneInfo("Europe/Berlin")
        de_hol = holidays.Germany(years=range(2019, 2027))
        me_de = month_end_days(date(2019, 8, 1), date(2026, 9, 30), de_hol)
        for exit_hm in ("17:29", "17:35"):
            rows = [(d, px["DE30m"].trade(at(d, "17:25", CET), at(d, exit_hm, CET), +1, 120), d in me_de)
                    for d in days if d not in de_hol and d >= date(2019, 9, 1)]
            res[f"Q4 {exit_hm}"] = summary(f"4 DAX month-end long 17:25-{exit_hm} Berlin", rows)

    rows = []
    for d in days:
        if d.weekday() != 4 or not 15 <= d.day <= 21 or d in us or d < date(2019, 9, 1):
            continue
        a, b = px["US500m"].mid(at(d, "12:00", NY)), px["US500m"].mid(at(d, "15:30", NY))
        if a is None or b is None:
            continue
        strike = round(b / 100) * 100
        if abs(b / strike - 1) > 0.002 or (strike - b) * (b - a) <= 0:      # near a strike and moving toward it
            continue
        side = -1 if strike > b else 1                                    # trade away from the strike
        rows.append((d, px["US500m"].trade(at(d, "15:45", NY), at(d, "16:15", NY), side, 200), True))
    res["Q5"] = summary("5 OpEx unpinning, US500 15:45-16:15 NY", rows)
    pd.to_pickle(res, ROOT / "results" / "flow_edges_ai.pkl")


if __name__ == "__main__":
    main()
