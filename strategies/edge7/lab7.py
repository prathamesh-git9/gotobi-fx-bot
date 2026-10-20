"""Round 7 (my half; Codex runs a broad technical edge hunt in codex_audit/edge_hunt). Rules fixed before running.

 O1 The overnight drift (Boyarchenko, Larsen & Whelan, RFS 2023; NY Fed SR 917): US equity index futures earn their
    largest positive returns 02:00-03:00 New York time, at the European open (+1.48 bp a day, 1998-2020), linked to
    dealers unloading the previous US close's order imbalance. Buy 02:00, sell 03:00 NY, every weekday.
    Catastrophe stop 0.5% (so 2% risk = 4x notional).
 O2 Same, only after a US sell-off: the previous cash session (15:58 NY close vs the 15:58 close before) fell.
 O3 Same, only when the last 30 minutes of the previous session (15:28 -> 15:58 NY) fell (end-of-day selling proxy;
    the paper uses signed futures volume, which a CFD feed does not have).
    US500, USTEC, US30.
 G1 Opening-gap fill: gap = 09:30 NY open vs the previous 15:58 close (DAX: 09:00 vs 17:25 Frankfurt). If
    0.15% <= |gap| <= 0.60%, fade it at the open: target = the previous close, stop = the same distance on the other
    side, out at 15:58 NY (DAX 17:25). US500, USTEC, US30, DE30.
 P  Portfolio of what already works, 2019-09 .. 2026-09, daily compounding:
    gotobi USDJPY bot at 6% risk (its replay trade list), gotobi long EURJPY at 3%, GBPUSD into the month-end fix at
    3%, NASDAQ noise-area momentum (lab6 B2 at today's spread) at half the paper's size. Compared with the gotobi bot
    alone. (EURJPY and GBPUSD rules as frozen in strategies/explore and strategies/month_end_fix.)

Pass for O/G rules: positive in both halves (to 2021 / from 2022), beats the same entries in a random direction,
t > 2.8.

  python strategies/edge7/lab7.py [O G P]
"""
import gc
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "different"))
sys.path.insert(0, str(ROOT / "strategies" / "breakouts"))
import lab4  # noqa: E402
from lab4 import M, report, run, tstat  # noqa: E402

UTC, NY, FRA = ZoneInfo("UTC"), ZoneInfo("America/New_York"), ZoneInfo("Europe/Berlin")
B8 = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
lab4.PIP.update({"USTECm": 1.0, "US500m": 0.1, "US30m": 1.0, "DE30m": 0.1})
OUT = {}


def load(sym):
    df = pd.read_parquet(ROOT / "data" / f"{sym}_m1.parquet", columns=B8)
    return df[(df.index >= "2019-08-01") & (df.index < "2026-10-01")]


def mid_at(m, ts, tol=3):
    i = m.i(ts, tol=tol)
    return None if i is None else (m.aopen[i] + m.bopen[i]) / 2


def O():
    for sym in ("US500m", "USTECm", "US30m"):
        m = M(load(sym), lab4.PIP[sym])
        gc.collect()
        closes = {}
        sigs = {"O1": [], "O2": [], "O3": []}
        days = [d.date() for d in pd.bdate_range("2019-08-05", "2026-09-30")]
        for d in days:
            c = mid_at(m, datetime.combine(d, time(15, 58), NY))
            c30 = mid_at(m, datetime.combine(d, time(15, 28), NY))
            if c is not None and c30 is not None:
                closes[d] = (c, c30)
        prev_days = sorted(closes)
        for n, d in enumerate(prev_days[1:], 1):
            p, pp = prev_days[n - 1], prev_days[n - 2] if n >= 2 else None
            nxt = d + timedelta(days=3 if d.weekday() == 4 else 1)        # the European open after session d
            i = m.i(datetime.combine(nxt, time(2, 0), NY), tol=2)
            j = m.i(datetime.combine(nxt, time(3, 0), NY), tol=2)
            if i is None or j is None:
                continue
            stop = 0.005 * m.aopen[i]
            sig = (i, j, +1, stop, None, 0.0)
            sigs["O1"].append(sig)
            if closes[d][0] < closes[p][0]:
                sigs["O2"].append(sig)
            if closes[d][0] < closes[d][1]:
                sigs["O3"].append(sig)
        names = {"O1": "European-open drift, every day", "O2": "European-open drift after a down US session",
                 "O3": "European-open drift after a down last half-hour"}
        for k, s in sigs.items():
            report(f"{k} {sym[:-1]} {names[k]}", *run(m, s))
        del m
        gc.collect()


def G():
    plan = {"US500m": (NY, time(9, 30), time(15, 58)), "USTECm": (NY, time(9, 30), time(15, 58)),
            "US30m": (NY, time(9, 30), time(15, 58)), "DE30m": (FRA, time(9, 0), time(17, 25))}
    for sym, (tz, t_open, t_close) in plan.items():
        m = M(load(sym), lab4.PIP[sym])
        gc.collect()
        sigs, prev_close = [], None
        for d in [x.date() for x in pd.bdate_range("2019-08-05", "2026-09-30")]:
            i = m.i(datetime.combine(d, t_open, tz), tol=1)
            j = m.i(datetime.combine(d, t_close, tz), tol=2)
            c = mid_at(m, datetime.combine(d, t_close, tz), tol=2)
            if i is not None and j is not None and prev_close is not None:
                o = (m.aopen[i] + m.bopen[i]) / 2
                gap = o / prev_close - 1
                if 0.0015 <= abs(gap) <= 0.006:
                    side = -1 if gap > 0 else +1
                    e = m.aopen[i] if side > 0 else m.bopen[i]
                    dist = abs(e - prev_close)
                    if dist > 0:
                        sigs.append((i, j, side, dist, dist, 0.0))
            prev_close = c if c is not None else prev_close
        report(f"G1 {sym[:-1]} opening-gap fill (0.15-0.60% gaps, 1:1)", *run(m, sigs))
        del m
        gc.collect()


# ------------------------------------------------------------------ portfolio of the keepers
def sleeve_gotobi():
    t = pd.read_csv(HERE / "gotobi_bot_trades_2016_2026.csv")
    t["d"] = pd.to_datetime(t.closed, utc=True).dt.tz_convert(None).dt.normalize()
    return t.groupby("d").r.sum()


def sleeve_eurjpy():
    sys.path.insert(0, str(ROOT / "strategies" / "explore"))
    import lab  # noqa: E402
    from lab import GotobiCalendar, XPx, tp_trade  # noqa: E402
    px = XPx("EURJPYm")
    got = GotobiCalendar().trade_days(date(2019, 8, 1), date(2026, 9, 30))
    rows = []
    for d in got:
        prev = d - timedelta(days=3 if d.weekday() == 0 else 1)
        e0 = datetime.combine(prev, time(15, 55), UTC) if d.weekday() else datetime.combine(d - timedelta(days=1), time(22, 15), UTC)
        p = tp_trade(px, e0, datetime.combine(d, time(0, 54), UTC), +1, 55, 30)
        if p is not None:
            rows.append((pd.Timestamp(d), p / 55))
    del px
    return pd.Series(dict(rows))


def sleeve_gbp_fix():
    sys.path.insert(0, str(ROOT / "src"))
    from flow_edges import LON, Px, at, month_end_days  # noqa: E402
    import holidays  # noqa: E402
    px = Px("GBPUSDm")
    me = sorted(month_end_days(date(2019, 8, 1), date(2026, 9, 30), holidays.UK(years=range(2019, 2027))))
    rows = [(pd.Timestamp(d), px.trade(at(d, "15:45", LON), at(d, "16:00", LON), +1, 25)) for d in me]
    del px
    return pd.Series({d: p / 25 for d, p in rows if p is not None})


def stats(daily, start, end):
    x = daily[(daily.index >= start) & (daily.index < end)]
    eq = 1000 * (1 + x).cumprod()
    yrs = (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25
    sh = x.mean() / x.std() * np.sqrt(252) if x.std() > 0 else np.nan
    return dict(eur=round(eq.iloc[-1]), cagr=round(((eq.iloc[-1] / 1000) ** (1 / yrs) - 1) * 100, 1),
                dd=round((1 - eq / eq.cummax()).max() * 100, 1), sharpe=round(sh, 2))


def P():
    import lab6  # noqa: E402
    import lab6_today_cost  # noqa: E402,F401  (today's spread for USTEC)
    nq = lab6.b2_daily("USTECm")[0]
    print("check, NASDAQ momentum at full size since Sep 2019 (lab6 today's-spread run said +11.9%/yr):",
          stats(nq, "2019-09-01", "2026-10-01"))
    s = {"gotobi USDJPY (6%)": sleeve_gotobi() * 0.06,
         "gotobi long EURJPY (3%)": sleeve_eurjpy() * 0.03,
         "GBPUSD month-end fix (3%)": sleeve_gbp_fix() * 0.03,
         "NASDAQ noise-area momentum (half size)": nq * 0.5}
    gc.collect()
    idx = pd.bdate_range("2019-09-02", "2026-09-30")
    df = pd.DataFrame({k: v.groupby(v.index.normalize()).sum().reindex(idx).fillna(0.0) for k, v in s.items()})
    print("\nP  daily-return correlations between sleeves:")
    print(df.corr().round(2).to_string())
    combos = {"gotobi bot alone (6%)": df[["gotobi USDJPY (6%)"]].sum(axis=1),
              "gotobi + EURJPY + GBP fix": df[["gotobi USDJPY (6%)", "gotobi long EURJPY (3%)", "GBPUSD month-end fix (3%)"]].sum(axis=1),
              "all four": df.sum(axis=1)}
    base = combos["gotobi bot alone (6%)"]
    for name in ("gotobi + EURJPY + GBP fix", "all four"):
        x = combos[name]
        k = base[base.index < "2022-01-01"].std() / x[x.index < "2022-01-01"].std()   # scale chosen on 2019-21 only
        combos[f"{name}, scaled to the bot's 2019-21 risk (x{k:.2f})"] = x * k
    for k in df.columns:
        combos.setdefault(k, df[k])
    print("\nP  EUR 1,000 compounded daily (per year, max drop, Sharpe):")
    for name, x in combos.items():
        a, b = stats(x, "2019-09-02", "2026-10-01"), stats(x, "2024-10-01", "2026-10-01")
        OUT[f"P {name}"] = dict(since_2019_09=a, last_2_years=b)
        print(f"   {name:42} since Sep 2019: EUR {a['eur']:>7,} ({a['cagr']:+5.1f}%/yr, drop {a['dd']:4.1f}%, Sharpe {a['sharpe']:.2f})"
              f" | last 2 yrs: EUR {b['eur']:>6,} ({b['cagr']:+5.1f}%/yr, drop {b['dd']:4.1f}%)")


if __name__ == "__main__":
    for k in sys.argv[1:] or ["O", "G", "P"]:
        globals()[k]()
        gc.collect()
    f = HERE / "lab7_results.json"
    old = json.loads(f.read_text()) if f.exists() else {}
    old.update({r["name"]: r for r in lab4.OUT})
    old.update(OUT)
    f.write_text(json.dumps(old, indent=1, default=str))
