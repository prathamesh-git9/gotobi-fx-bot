"""Reproducible, bid/ask, one-minute study of scheduled-flow windows.

Run: python research.py
Only the explicitly permitted source parquet files are read. Outputs stay here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
from scipy import stats


ROOT = Path(__file__).resolve().parent
DATA = Path(r"E:\Projects\New folder\liquidity_sweep\data")
CUTOFF = pd.Timestamp("2026-10-01", tz="UTC")


@dataclass(frozen=True)
class Idea:
    name: str
    file: str
    zone: str
    hour: int
    minute: int
    hold: int
    schedule: str
    control_hour: int | None = None
    control_minute: int | None = None
    unit: float = 1.0
    unit_name: str = "points"
    signal: str | None = None


IDEAS = [
    Idea("EURUSD London month-end FX fix", "EURUSDm_m1.parquet", "Europe/London", 15, 30, 30, "month_end", unit=.0001, unit_name="pips"),
    Idea("GBPUSD London month-end FX fix", "GBPUSDm_m1.parquet", "Europe/London", 15, 30, 30, "month_end", unit=.0001, unit_name="pips"),
    Idea("USDJPY London month-end FX fix", "USDJPYm_m1.parquet", "Europe/London", 15, 30, 30, "month_end", unit=.01, unit_name="pips"),
    Idea("Gold London AM fix", "XAUUSDm_m1.parquet", "Europe/London", 10, 0, 30, "daily", 11, 0, 1, "USD/oz"),
    Idea("Gold London PM fix", "XAUUSDm_m1.parquet", "Europe/London", 14, 30, 30, "daily", 13, 30, 1, "USD/oz"),
    Idea("US500 month-end close", "US500m_m1.parquet", "America/New_York", 15, 30, 29, "month_end", unit=1, unit_name="index points"),
    Idea("US500 quarter-end close", "US500m_m1.parquet", "America/New_York", 15, 30, 29, "quarter_end", unit=1, unit_name="index points"),
    Idea("USTEC quarter-end close", "USTECm_m1.parquet", "America/New_York", 15, 30, 29, "quarter_end", unit=1, unit_name="index points"),
    Idea("EURUSD month-end US equity hedge", "EURUSDm_m1.parquet", "Europe/London", 15, 30, 30, "month_end", unit=.0001, unit_name="pips", signal="spy"),
    Idea("GBPUSD month-end US equity hedge", "GBPUSDm_m1.parquet", "Europe/London", 15, 30, 30, "month_end", unit=.0001, unit_name="pips", signal="spy"),
    Idea("USDJPY month-end US equity hedge", "USDJPYm_m1.parquet", "Europe/London", 15, 30, 30, "month_end", unit=.01, unit_name="pips", signal="spy_inverse"),
    Idea("US500 quarterly index rebalance", "US500m_m1.parquet", "America/New_York", 15, 30, 29, "third_friday_q", unit=1, unit_name="index points"),
    Idea("USTEC quarterly index rebalance", "USTECm_m1.parquet", "America/New_York", 15, 30, 29, "third_friday_q", unit=1, unit_name="index points"),
]


def load_bars(filename: str) -> pd.DataFrame:
    cols = ["Timestamp", "bopen", "bhigh", "blow", "aopen", "ahigh", "alow"]
    files = [DATA / filename]
    if filename == "USDJPYm_m1.parquet":
        files.insert(0, DATA / "USDJPYm_2016_m1.parquet")
    if filename == "XAUUSDm_m1.parquet":
        files.insert(0, DATA / "XAUUSDm_2015_m1.parquet")
    frames = []
    for f in files:
        part = pd.read_parquet(f, columns=cols)
        frames.append(part.reset_index() if "Timestamp" not in part.columns else part)
    df = pd.concat(frames, ignore_index=True).sort_values("Timestamp")
    df["Timestamp"] = pd.to_datetime(df["Timestamp"], utc=True)
    df = df.loc[df.Timestamp < CUTOFF]
    df = df.drop_duplicates("Timestamp", keep="first").reset_index(drop=True)
    if not df.Timestamp.is_monotonic_increasing or (df.aopen < df.bopen).any():
        raise ValueError(f"Bad timestamp or inverted spread: {filename}")
    return df


def business_end(dates: pd.DatetimeIndex, quarter: bool = False) -> np.ndarray:
    # Calendar last weekday is known in advance. A market holiday with no bar is skipped.
    period = dates.to_period("Q" if quarter else "M")
    ends = period.end_time.normalize().to_numpy(dtype="datetime64[D]")
    weekdays = (pd.DatetimeIndex(ends).dayofweek.to_numpy() + 1) % 7
    # Mon=1 ... Fri=5, Sat=6, Sun=0 under this transform.
    shift = np.where(weekdays == 6, 1, np.where(weekdays == 0, 2, 0))
    return dates.normalize().to_numpy(dtype="datetime64[D]") == ends - shift.astype("timedelta64[D]")


def third_friday_q(dates: pd.DatetimeIndex) -> np.ndarray:
    return ((dates.month % 3 == 0) & (dates.dayofweek == 4) & (dates.day >= 15) & (dates.day <= 21))


def event_table(df: pd.DataFrame, idea: Idea) -> pd.DataFrame:
    t = pd.DatetimeIndex(df.Timestamp)
    local = t.tz_convert(idea.zone)
    utc_days = t.normalize()
    ranges = pd.DataFrame({"day": utc_days, "range_high": df.bhigh.to_numpy(), "range_low": df.blow.to_numpy()})
    daily = ranges.groupby("day").agg({"range_high": "max", "range_low": "min"})
    # Prior 20 observed UTC days only. Missing calendar days do not leak future bars.
    risk = ((daily.range_high - daily.range_low).rolling(20, min_periods=10).median().shift(1) * .15)
    lookup_risk = risk.reindex(utc_days).to_numpy()
    clock = (local.hour == idea.hour) & (local.minute == idea.minute)
    control_clock = clock if idea.control_hour is None else ((local.hour == idea.control_hour) & (local.minute == idea.control_minute))
    idx = np.flatnonzero(clock | control_clock)
    dates = local[idx].tz_localize(None).normalize()
    if idea.schedule == "daily":
        sched = np.ones(len(idx), bool)
    elif idea.schedule == "third_friday_q":
        sched = third_friday_q(dates)
    else:
        sched = business_end(dates, idea.schedule == "quarter_end")
    is_event = clock[idx] & sched
    if idea.schedule == "quarter_end":
        ordinary = ~business_end(dates)
    else:
        ordinary = ~sched if idea.schedule != "daily" else True
    is_control = control_clock[idx] & ordinary
    keep = is_event | is_control
    idx, dates, is_event = idx[keep], dates[keep], is_event[keep]
    ns = t.as_unit("ns").asi8
    out = []
    bopen, bhigh, blow = [df[c].to_numpy() for c in ("bopen", "bhigh", "blow")]
    aopen, ahigh, alow = [df[c].to_numpy() for c in ("aopen", "ahigh", "alow")]
    minute_ns = 60_000_000_000
    for j, d, ev in zip(idx, dates, is_event):
        stop = lookup_risk[j]
        if not np.isfinite(stop) or stop <= 0:
            continue
        k = np.searchsorted(ns, ns[j] + idea.hold * minute_ns)
        if k >= len(ns) or ns[k] != ns[j] + idea.hold * minute_ns:
            continue
        # Require all intermediate bars, so gaps cannot hide stop/target touches.
        if k - j != idea.hold:
            continue
        for side in (1, -1):
            entry = aopen[j] if side == 1 else bopen[j]
            if side == 1:
                stops = np.flatnonzero(blow[j:k] <= entry - stop)
                targets = np.flatnonzero(bhigh[j:k] >= entry + stop)
            else:
                stops = np.flatnonzero(ahigh[j:k] >= entry + stop)
                targets = np.flatnonzero(alow[j:k] <= entry - stop)
            first_stop = int(stops[0]) if len(stops) else idea.hold
            first_target = int(targets[0]) if len(targets) else idea.hold
            if first_stop <= first_target and first_stop < idea.hold:
                pnl = -stop
            elif first_target < first_stop:
                pnl = stop
            else:
                pnl = (bopen[k] - entry) if side == 1 else (entry - aopen[k])
            out.append((d, bool(ev), side, pnl / idea.unit, pnl / stop, stop / idea.unit))
    return pd.DataFrame(out, columns=["date", "event", "side", "pnl", "r", "stop"])


def t_p(x: np.ndarray) -> tuple[float, float]:
    if len(x) < 2 or np.std(x, ddof=1) == 0:
        return math.nan, math.nan
    z = stats.ttest_1samp(x, 0)
    return float(z.statistic), float(z.pvalue)


def diff_t_p(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 2 or len(y) < 2:
        return math.nan, math.nan
    z = stats.ttest_ind(x, y, equal_var=False)
    return float(z.statistic), float(z.pvalue)


def summary(x: pd.DataFrame, control: pd.DataFrame, paired: bool = False) -> dict:
    a, b = x.pnl.to_numpy(), control.pnl.to_numpy()
    t, p = t_p(a)
    if paired:
        pairs = x[["date", "pnl"]].merge(control[["date", "pnl"]], on="date", suffixes=("_event", "_control"))
        dt, dp = t_p((pairs.pnl_event - pairs.pnl_control).to_numpy())
    else:
        dt, dp = diff_t_p(a, b)
    return {"n": len(a), "mean": float(np.mean(a)) if len(a) else math.nan,
            "total": float(np.sum(a)), "t": t, "p_two_sided": p,
            "control_n": len(b), "control_mean": float(np.mean(b)) if len(b) else math.nan,
            "diff_t": dt, "diff_p_two_sided": dp,
            "by_year": {str(k): round(float(v), 4) for k, v in x.groupby(x.date.dt.year).pnl.sum().items()}}


def compound(df: pd.DataFrame, start: str, risk_fraction: float = .005) -> dict:
    sub = df[(df.date >= pd.Timestamp(start)) & (df.date < pd.Timestamp("2026-10-01"))].sort_values("date")
    balance, peak, max_dd = 1000.0, 1000.0, 0.0
    yearly = {}
    for row in sub.itertuples():
        balance *= max(0.0, 1.0 + risk_fraction * row.r)
        peak = max(peak, balance)
        max_dd = max(max_dd, 1.0 - balance / peak)
        yearly[row.date.year] = yearly.get(row.date.year, 0.0) + row.r
    worst = min(yearly, key=yearly.get) if yearly else None
    return {"start": start, "final_balance": round(balance, 2), "max_drawdown_pct": round(max_dd * 100, 2),
            "trades": len(sub), "worst_year": worst, "worst_year_r": round(yearly[worst], 3) if worst else None}


def main() -> None:
    output = []
    cache = {}
    yahoo = pd.read_parquet(DATA / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    spy = yahoo.loc[yahoo.sym == "SPY", ["date", "close"]].sort_values("date").copy()
    spy["date"] = spy.date.astype("datetime64[us]")
    spy["direction"] = np.sign(spy.close / spy.close.shift(20) - 1)
    spy = spy[["date", "direction"]]
    for idea in IDEAS:
        print("Testing", idea.name, flush=True)
        if idea.file not in cache:
            cache[idea.file] = load_bars(idea.file)
        trades = event_table(cache[idea.file], idea)
        if idea.signal:
            trades = pd.merge_asof(trades.sort_values("date"), spy, on="date", direction="backward", allow_exact_matches=False)
            direction = trades.direction if idea.signal == "spy" else -trades.direction
            trades = trades[(direction != 0) & (trades.side == direction)].drop(columns="direction")
        train = trades[(trades.date >= pd.Timestamp("2016-01-01")) & (trades.date < pd.Timestamp("2022-01-01"))]
        if idea.signal:
            side = None
            test = trades[(trades.date >= pd.Timestamp("2022-01-01")) & (trades.date < pd.Timestamp("2026-10-01"))]
        else:
            # A single training choice per idea: direction with larger event mean.
            means = train[train.event].groupby("side").pnl.mean()
            side = int(means.idxmax())
            train = train[train.side == side]
            test = trades[(trades.date >= pd.Timestamp("2022-01-01")) & (trades.date < pd.Timestamp("2026-10-01")) & (trades.side == side)]
        result = {"idea": idea.name, "file": idea.file, "side": "SPY conditional" if side is None else ("buy" if side == 1 else "sell"), "unit": idea.unit_name,
                  "entry_local": f"{idea.hour:02d}:{idea.minute:02d}", "hold_minutes": idea.hold,
                  "train": summary(train[train.event], train[~train.event], idea.schedule == "daily"),
                  "test": summary(test[test.event], test[~test.event], idea.schedule == "daily")}
        # Two-sided p < .05 for positive expectancy and positive event-control difference;
        # family-wise Bonferroni gate over the full list of ideas.
        q = result["test"]
        result["survives"] = bool(q["mean"] > 0 and q["t"] > 0 and q["diff_t"] > 0
                                  and q["p_two_sided"] < .05 / len(IDEAS)
                                  and q["diff_p_two_sided"] < .05 / len(IDEAS))
        if result["survives"]:
            chosen = trades[trades.event] if side is None else trades[(trades.side == side) & trades.event]
            first = str(chosen.date.min().date())
            result["compound"] = [compound(chosen, first), compound(chosen, "2025-01-01")]
        output.append(result)
        print("  train/test event n:", result["train"]["n"], result["test"]["n"], "test mean:", round(q["mean"], 3), "survives:", result["survives"], flush=True)
    (ROOT / "results.json").write_text(json.dumps(output, indent=2, allow_nan=True), encoding="utf-8")
    print("Wrote results.json")


if __name__ == "__main__":
    main()
