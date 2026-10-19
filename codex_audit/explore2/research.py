"""Pre-specified scheduled-flow study. See RULES.md before interpreting output."""
from __future__ import annotations

import json
from pathlib import Path
from datetime import timedelta

import holidays
import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
DATA = Path(r"E:/Projects/New folder/liquidity_sweep/data")
CUTOFF = pd.Timestamp("2026-10-01", tz="UTC")
NY = "America/New_York"
TOKYO = "Asia/Tokyo"
COLS = ["bopen", "bclose", "aopen", "aclose"]
FILES = {
    "EURUSD": ["EURUSDm_2016_m1.parquet", "EURUSDm_m1.parquet"],
    "GBPUSD": ["GBPUSDm_2016_m1.parquet", "GBPUSDm_m1.parquet"],
    "USDJPY": ["USDJPYm_2016_m1.parquet", "USDJPYm_m1.parquet"],
    "XAUUSD": ["XAUUSDm_2015_m1.parquet", "XAUUSDm_m1.parquet"],
    "US500": ["US500m_m1.parquet"],
    "US30": ["US30m_m1.parquet"],
    "USTEC": ["USTECm_m1.parquet"],
}
EVENTS = pd.read_csv(DATA / "events_calendar.csv")
NY_HOL = holidays.NYSE(years=range(2015, 2027))
JP_HOL = holidays.Japan(years=range(2006, 2027))


def utc(local_date, hour, zone):
    return (pd.Timestamp(local_date).tz_localize(zone) + pd.Timedelta(hours=hour)).tz_convert("UTC")


def load(sym):
    files = FILES[sym] if sym != "USDJPY_HD" else ["histdata/USDJPY_hd_model_2006_2015_m1.parquet"]
    frames = [pd.read_parquet(DATA / f, columns=COLS) for f in files]
    frame = pd.concat(frames).sort_index()
    frame.index = pd.DatetimeIndex(frame.index).tz_localize("UTC")
    frame = frame.loc[~frame.index.duplicated(keep="last")]
    frame = frame.loc[frame.index < CUTOFF]
    return frame


def quote(frame, at, max_lag=5, direction="forward"):
    at = pd.Timestamp(at).tz_convert("UTC")
    idx = frame.index.searchsorted(at, side="left" if direction == "forward" else "right")
    if direction == "backward":
        idx -= 1
    if idx < 0 or idx >= len(frame):
        return None
    actual = frame.index[idx]
    lag = (actual - at).total_seconds() / 60 if direction == "forward" else (at - actual).total_seconds() / 60
    if lag < 0 or lag > max_lag:
        return None
    return actual, frame.iloc[idx]


def trade(frame, entry, exit_, side, sym, group, tag, control=None):
    q0, q1 = quote(frame, entry), quote(frame, exit_)
    if q0 is None or q1 is None or q0[0] >= q1[0]:
        return None
    t0, a = q0
    t1, b = q1
    middle = (a.bopen + a.aopen) / 2
    pnl = (b.bopen - a.aopen) if side == 1 else (a.bopen - b.aopen)
    # Estimated financing on long index CFD notional.
    hours = (t1 - t0).total_seconds() / 3600
    financing = middle * 0.06 * hours / (365 * 24) if sym.startswith("US") and sym != "USDJPY" else 0
    pnl -= financing
    scale = 10000 if sym in ("EURUSD", "GBPUSD") else (100 if sym == "USDJPY" else 1)
    return dict(group=group, tag=tag, sym=sym, entry=str(t0), exit=str(t1), year=t0.year,
                pnl=float(pnl), net=float(pnl / middle), units=float(pnl * scale),
                financing=float(financing), control=control)


def paired(frame, entry, exit_, side, sym, group, tag, c_entry, c_exit):
    e = trade(frame, entry, exit_, side, sym, group, tag)
    c = trade(frame, c_entry, c_exit, side, sym, group, tag)
    if e is not None and c is not None:
        e["control"] = c["net"]
        return e
    return None


def business_days(start, end, holiday):
    return [d for d in pd.date_range(start, end, freq="D") if d.weekday() < 5 and d.date() not in holiday]


def build_fomc(frame, sym):
    out = []
    fomc_days = {str(pd.Timestamp(t, tz="UTC").tz_convert(NY).date()) for t in EVENTS.loc[EVENTS.event == "fomc", "time_utc"]}
    for row in EVENTS.loc[EVENTS.event == "fomc"].itertuples():
        release = pd.Timestamp(row.time_utc, tz="UTC")
        if release >= CUTOFF:
            continue
        ny_day = release.tz_convert(NY).date()
        prev = pd.Timestamp(ny_day) - pd.Timedelta(days=1)
        if prev.weekday() >= 5:
            continue
        entry = utc(prev.date(), 14, NY)
        exit_ = release - pd.Timedelta(minutes=15)
        if str((release - pd.Timedelta(days=7)).tz_convert(NY).date()) in fomc_days:
            continue
        x = paired(frame, entry, exit_, 1, sym, "fomc", sym,
                   entry - pd.Timedelta(days=7), exit_ - pd.Timedelta(days=7))
        if x:
            out.append(x)
    return out


def build_holiday(frame, hour):
    out = []
    preholidays = set()
    for h in list(NY_HOL):
        d = pd.Timestamp(h) - pd.Timedelta(days=1)
        while d.weekday() >= 5 or d.date() in NY_HOL:
            d -= pd.Timedelta(days=1)
        preholidays.add(d.date())
    for h in sorted(NY_HOL):
        if h.weekday() >= 5:
            continue
        prior = pd.Timestamp(h) - pd.Timedelta(days=1)
        while prior.weekday() >= 5 or prior.date() in NY_HOL:
            prior -= pd.Timedelta(days=1)
        entry, exit_ = utc(prior.date(), hour, NY), utc(prior.date(), 16, NY)
        control_day = (prior - pd.Timedelta(days=7)).date()
        if control_day in NY_HOL or control_day in preholidays:
            continue
        x = paired(frame, entry, exit_, 1, "US500", "holiday", str(hour),
                   entry - pd.Timedelta(days=7), exit_ - pd.Timedelta(days=7))
        if x:
            out.append(x)
    return out


def build_toshin(frame, n):
    out = []
    start = frame.index.min().tz_convert(TOKYO).date()
    for month in pd.period_range(str(start)[:7], "2026-09", freq="M"):
        days = business_days(month.start_time, month.end_time, JP_HOL)
        for i in range(min(n, len(days) - 5)):
            d, c = days[i], days[i + 5]
            x = paired(frame, utc(d.date(), 9, TOKYO), utc(d.date(), 10, TOKYO), 1,
                       "USDJPY", "toshin", str(n), utc(c.date(), 9, TOKYO), utc(c.date(), 10, TOKYO))
            if x:
                out.append(x)
    return out


def build_repat(frame, mode):
    out = []
    start = frame.index.min().tz_convert(TOKYO).year
    for year in range(start, 2027):
        for month in ([3, 9] if mode != "reversal" else [4, 10]):
            p = pd.Period(f"{year}-{month:02d}", freq="M")
            days = business_days(p.start_time, p.end_time, JP_HOL)
            if not days:
                continue
            if mode == "reversal":
                event_days, control_days, side = days[:5], days[5:10], 1
            else:
                n = int(mode)
                event_days, control_days, side = days[-n:], days[:n], -1
            for d, c in zip(event_days, control_days):
                x = paired(frame, utc(d.date(), 9, TOKYO), utc(d.date(), 17, TOKYO), side,
                           "USDJPY", "repat", mode, utc(c.date(), 9, TOKYO), utc(c.date(), 17, TOKYO))
                if x:
                    out.append(x)
    return out


def build_boj(frame):
    out = []
    boj_dates = set(EVENTS.loc[EVENTS.event == "boj", "date"])
    for ds in sorted(boj_dates):
        d = pd.Timestamp(ds)
        if d >= pd.Timestamp("2026-10-01"):
            continue
        prior = d - pd.Timedelta(days=7)
        if str(prior.date()) in boj_dates:
            continue
        x = paired(frame, utc(d.date(), 8, TOKYO), utc(d.date(), 11, TOKYO), 1,
                   "USDJPY", "boj", "USDJPY", utc(prior.date(), 8, TOKYO), utc(prior.date(), 11, TOKYO))
        if x:
            out.append(x)
    return out


def build_gap(frame, sym, side_mode, duration):
    out = []
    start = frame.index.min().date()
    for sunday in pd.date_range(start, "2026-09-30", freq="W-SUN", tz="UTC"):
        friday = sunday - pd.Timedelta(days=2)
        fq = quote(frame, friday + pd.Timedelta(hours=22), 240, "backward")
        sq = quote(frame, sunday + pd.Timedelta(hours=22), 240, "forward")
        if fq is None or sq is None:
            continue
        ft, a = fq
        st, b = sq
        gap = (b.bopen + b.aopen - a.bclose - a.aclose) / 2
        spread = a.aopen - a.bopen
        if abs(gap) <= spread:
            continue
        side = -np.sign(gap) if side_mode == "fade" else np.sign(gap)
        entry, exit_ = st + pd.Timedelta(hours=1), st + pd.Timedelta(hours=duration + 1)
        x = paired(frame, entry, exit_, int(side), sym, "gap", f"{sym}_{side_mode}_{duration}",
                   entry + pd.Timedelta(days=1), exit_ + pd.Timedelta(days=1))
        if x:
            out.append(x)
    return out


def period(rows, label):
    if label == "train":
        return [x for x in rows if x["year"] <= 2021 and x["year"] >= 2016]
    if label == "holdout":
        return [x for x in rows if 2022 <= x["year"] <= 2026]
    if label == "old":
        return [x for x in rows if x["year"] <= 2015]
    return rows


def calc(rows):
    n = len(rows)
    if not n:
        return dict(n=0, mean=None, t=None, p=None, control_t=None, control_p=None, annual_units={})
    r = np.array([x["net"] for x in rows])
    diff = r - np.array([x["control"] for x in rows])
    def test(a):
        if len(a) < 2 or np.std(a, ddof=1) == 0:
            return None, None
        t = float(np.mean(a) / (np.std(a, ddof=1) / np.sqrt(len(a))))
        return t, float(stats.t.sf(t, len(a) - 1))
    t, p = test(r)
    ct, cp = test(diff)
    annual = {}
    for x in rows:
        annual[str(x["year"])] = annual.get(str(x["year"]), 0) + x["units"]
    return dict(n=n, mean=float(np.mean(r)), t=t, p=p, control_mean=float(np.mean(diff)),
                control_t=ct, control_p=cp, annual_units={k: round(v, 2) for k, v in annual.items()})


def equity(rows):
    rows = sorted(rows, key=lambda x: x["entry"])
    balance, peak, dd = 1000.0, 1000.0, 0.0
    years = {}
    for x in rows:
        old = balance
        balance *= 1 + 2 * x["net"]
        peak = max(peak, balance)
        dd = max(dd, 1 - balance / peak)
        y = str(x["year"])
        if y not in years:
            years[y] = [old, balance]
        years[y][1] = balance
    yr = {y: v[1] / v[0] - 1 for y, v in years.items()}
    return dict(final=round(balance, 2), max_drawdown=round(dd, 4), trades=len(rows),
                worst_year=min(yr, key=yr.get) if yr else None,
                worst_year_return=round(min(yr.values()), 4) if yr else None)


def main():
    candidates = {x: {} for x in ["fomc", "holiday", "toshin", "repat", "gap", "boj"]}
    for sym in FILES:
        print("loading", sym, flush=True)
        frame = load(sym)
        if sym in ["US500", "US30", "USTEC", "USDJPY", "EURUSD", "XAUUSD"]:
            candidates["fomc"][sym] = build_fomc(frame, sym)
        if sym == "US500":
            for h in (12, 14, 15):
                candidates["holiday"][str(h)] = build_holiday(frame, h)
        if sym == "USDJPY":
            for n in (1, 2, 3):
                candidates["toshin"][str(n)] = build_toshin(frame, n)
            for mode in ("5", "10", "reversal"):
                candidates["repat"][mode] = build_repat(frame, mode)
            candidates["boj"]["USDJPY"] = build_boj(frame)
        if sym in ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]:
            for mode in ("fade", "follow"):
                for h in (4, 12):
                    key = f"{sym}_{mode}_{h}"
                    candidates["gap"][key] = build_gap(frame, sym, mode, h)
        del frame
    # Historical check is built only after every candidate and selection score is fixed.
    selected = {}
    for idea, choices in candidates.items():
        def score(item):
            x = calc(period(item[1], "train"))["t"]
            return -1e9 if x is None else x
        selected[idea] = max(choices.items(), key=score)[0]
    print("selected", selected, flush=True)
    hd = load("USDJPY_HD")
    old = {
        "toshin": build_toshin(hd, int(selected["toshin"])),
        "repat": build_repat(hd, selected["repat"]),
        "boj": build_boj(hd),
    }
    report = {"selection": selected, "threshold": 0.05 / 6, "ideas": {}, "survivors": {}}
    for idea, choices in candidates.items():
        report["ideas"][idea] = {"candidates": {key: {"train": calc(period(rows, "train")),
                                                         "holdout": calc(period(rows, "holdout"))}
                                               for key, rows in choices.items()}}
        key = selected[idea]
        hold = calc(period(choices[key], "holdout"))
        old_stats = calc(period(old[idea], "old")) if idea in old else None
        report["ideas"][idea]["old"] = old_stats
        survives = (hold["n"] >= 20 and hold["p"] is not None and hold["p"] < 0.05 / 6
                    and hold["control_p"] is not None and hold["control_p"] < 0.05 / 6
                    and (old_stats is None or old_stats["mean"] is not None and old_stats["mean"] > 0))
        report["ideas"][idea]["survives"] = bool(survives)
        if survives:
            rows = choices[key]
            report["survivors"][idea] = {
                "full": equity(rows),
                "recent": equity([x for x in rows if x["entry"] >= "2025-01-01"]),
            }
    (HERE / "results.json").write_text(json.dumps(report, indent=2))
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
