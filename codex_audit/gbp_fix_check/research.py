"""Independent, fixed-rule audit of the GBP/USD London month-end fixing trade.

Run: python research.py
Reads the named source parquet files only and writes results.json beside this file.
"""
from __future__ import annotations

import json
from pathlib import Path

import holidays
import numpy as np
import pandas as pd
from scipy.stats import t as student_t


HERE = Path(__file__).resolve().parent
ROOT = Path("E:/Projects/New folder/liquidity_sweep")
DATA = ROOT / "data"
HIST = ROOT / "strategies/month_end_fix/data"
PIP = 0.0001
END = pd.Timestamp("2026-10-01")
UK = holidays.UK(years=range(2006, 2027))
RNG = np.random.default_rng(20261019)


def business_days() -> pd.DatetimeIndex:
    dates = pd.date_range("2006-01-01", "2026-09-30", freq="D")
    return dates[(dates.dayofweek < 5) & np.array([x.date() not in UK for x in dates])]


BDAYS = business_days()
LAST = BDAYS.to_series().groupby(BDAYS.to_period("M")).max().to_numpy(dtype="datetime64[ns]")
LAST = pd.DatetimeIndex(LAST)


def sources(pair: str):
    yield HIST / f"{pair}_hd_bid_m1.parquet", "hist"
    p = pair + "m"
    yield DATA / f"{p}_2016_m1.parquet", "exness"
    yield DATA / f"{p}_m1.parquet", "exness"
    final = DATA / ("GBPUSDm_2026_m1.parquet" if pair == "GBPUSD" else "EURUSDm_2026_10_m1.parquet")
    yield final, "exness"


def load(pair: str) -> tuple[pd.DataFrame, dict]:
    parts = []
    spans = {}
    for path, feed in sources(pair):
        cols = ["bopen", "blow"] + (["aopen"] if feed == "exness" else [])
        raw = pd.read_parquet(path, columns=cols)
        spans[path.name] = [str(raw.index.min()), str(raw.index.max()), len(raw)]
        # Keep only minutes that can enter or stop any specified 15-minute trade.
        raw = raw[(raw.index >= "2006-01-01") & (raw.index < END)]
        raw = raw[(raw.index.hour >= 13) & (raw.index.hour <= 17)].copy()
        raw["feed"] = feed
        parts.append(raw)
    bars = pd.concat(parts).sort_index(kind="stable")
    duplicate_count = int(bars.index.duplicated().sum())
    duplicates = bars[bars.index.duplicated(keep=False)]
    duplicate_disagreements = 0
    if len(duplicates):
        a = duplicates.groupby(level=0).first()[["bopen", "blow", "aopen"]]
        z = duplicates.groupby(level=0).last()[["bopen", "blow", "aopen"]]
        duplicate_disagreements = int(((a - z).abs() > 1e-9).any(axis=1).sum())
    bars = bars[~bars.index.duplicated(keep="first")]
    bars.index = bars.index.tz_localize("UTC").tz_convert("Europe/London")
    bars["date"] = bars.index.date
    bars["minute"] = bars.index.hour * 60 + bars.index.minute
    spread_sample = bars[(bars["minute"] == 15 * 60 + 45) & (bars["feed"] == "exness")]
    spread_sample = spread_sample[spread_sample.index.year <= 2021]
    spread = (spread_sample.aopen - spread_sample.bopen) / PIP
    modeled = round(float(spread.median()), 1)
    bars.loc[bars.feed == "hist", "aopen"] = bars.loc[bars.feed == "hist", "bopen"] + modeled * PIP
    return bars, {"sources": spans, "duplicates": duplicate_count,
                  "duplicate_disagreements": duplicate_disagreements,
                  "model_spread_pips": modeled, "spread_sample_n": len(spread),
                  "spread_quantiles": {str(k): round(float(v), 3) for k, v in spread.quantile([.1, .5, .9, .99]).items()}}


def trades(bars: pd.DataFrame, entry: str = "15:45", exit: str = "16:00",
           stop: float | None = 25, extra_spread: float = 0,
           slip: float = 0) -> pd.DataFrame:
    em = int(entry[:2]) * 60 + int(entry[3:])
    xm = int(exit[:2]) * 60 + int(exit[3:])
    assert xm > em
    e = bars[bars.minute == em][["date", "bopen", "aopen", "feed"]].copy()
    x = bars[bars.minute == xm][["date", "bopen"]].copy()
    e = e.set_index("date").rename(columns={"bopen": "entry_bid", "aopen": "entry_ask"})
    x = x.set_index("date").rename(columns={"bopen": "exit_bid"})
    out = e.join(x, how="inner")
    # A higher ask reduces profit and raises the absolute stop threshold.
    ask = out.entry_ask + extra_spread * PIP
    out["raw_pips"] = (out.exit_bid - ask) / PIP
    lows = bars[(bars.minute >= em) & (bars.minute < xm)].groupby("date").blow.min()
    out = out.join(lows.rename("low"))
    out["stopped"] = (out.low <= ask - stop * PIP) if stop is not None else False
    out["pips"] = np.where(out.stopped, -stop - slip, out.raw_pips) if stop is not None else out.raw_pips
    out.index = pd.to_datetime(out.index)
    out["year"] = out.index.year
    return out


def summary(df: pd.DataFrame) -> dict:
    vals = df.pips.to_numpy()
    n = len(vals)
    sem = vals.std(ddof=1) / np.sqrt(n) if n > 1 else np.nan
    ci = student_t.ppf(.975, n - 1) * sem if n > 1 else np.nan
    return {"n": n, "mean": round(float(vals.mean()), 3) if n else None,
            "total": round(float(vals.sum()), 2),
            "t": round(float(vals.mean() / sem), 3) if n > 1 and sem else None,
            "ci95_mean": [round(float(vals.mean() - ci), 3), round(float(vals.mean() + ci), 3)] if n > 1 else None,
            "win_pct": round(float((vals > 0).mean() * 100), 2) if n else None,
            "stops": int(df.stopped.sum()) if "stopped" in df else 0}


def period(df: pd.DataFrame, a: int, b: int) -> dict:
    return summary(df[(df.year >= a) & (df.year <= b)])


def calendar_weekday_month_end() -> pd.DatetimeIndex:
    dates = pd.date_range("2006-01-01", "2026-09-30", freq="B")
    return pd.DatetimeIndex(dates.to_series().groupby(dates.to_period("M")).max().to_numpy(dtype="datetime64[ns]"))


def audit_pair(pair: str) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    bars, meta = load(pair)
    all_days = trades(bars)
    me = all_days.loc[all_days.index.isin(LAST)]
    others = all_days.loc[~all_days.index.isin(LAST) & all_days.index.isin(BDAYS)]
    result = {"meta": meta, "main": summary(me), "other_business_days": summary(others),
              "other_business_days_since_2016": period(others, 2016, 2026),
              "other_business_days_since_2025": period(others, 2025, 2026),
              "since_2016": period(me, 2016, 2026),
              "since_2025": period(me, 2025, 2026),
              "periods": {"2006-15": period(me, 2006, 2015),
                          "2016-21": period(me, 2016, 2021),
                          "2022-26": period(me, 2022, 2026)},
              "per_year": {str(y): summary(g) for y, g in me.groupby("year")},
              "missing_month_ends": [str(d.date()) for d in LAST if d not in me.index],
              "month_end_trades": [{"date": str(d.date()), "pips": round(float(row.pips), 3),
                                     "feed": row.feed, "stopped": bool(row.stopped)}
                                    for d, row in me.iterrows()]}
    counts = bars[(bars.minute >= 15 * 60 + 45) & (bars.minute < 16 * 60)].groupby("date").size()
    result["incomplete_intervals"] = {str(d.date()): int(counts.get(d.date(), 0))
                                       for d in me.index if counts.get(d.date(), 0) < 15}
    if pair == "GBPUSD":
        result["times"] = {f"{a}-{z}": summary(trades(bars, a, z).loc[lambda f: f.index.isin(LAST)])
                           for a, z in [("14:45", "15:00"), ("16:15", "16:30")]}
        scenarios = [("entry_1540", "15:40", "16:00", 25, 0, 0),
                     ("entry_1550", "15:50", "16:00", 25, 0, 0),
                     ("exit_1558", "15:45", "15:58", 25, 0, 0),
                     ("exit_1602", "15:45", "16:02", 25, 0, 0),
                     ("stop_15", "15:45", "16:00", 15, 0, 0),
                     ("stop_40", "15:45", "16:00", 40, 0, 0),
                     ("no_stop", "15:45", "16:00", None, 0, 0),
                     ("spread_plus_0_5", "15:45", "16:00", 25, .5, 0),
                     ("spread_plus_1", "15:45", "16:00", 25, 1, 0),
                     ("stop_slip_3", "15:45", "16:00", 25, 0, 3)]
        scenario_trades = {name: trades(bars, a, z, s, sp, sl).loc[lambda f: f.index.isin(LAST)]
                           for name, a, z, s, sp, sl in scenarios}
        result["robustness"] = {name: summary(df) for name, df in scenario_trades.items()}
        result["modern_robustness"] = {name: {"since_2016": period(df, 2016, 2026),
                                              "since_2025": period(df, 2025, 2026)}
                                        for name, df in scenario_trades.items()}
        result["robustness"]["exclude_best_5"] = summary(me.drop(me.nlargest(5, "pips").index))
        result["robustness"]["last_calendar_weekday"] = summary(all_days.loc[all_days.index.isin(calendar_weekday_month_end())])
        result["calendar_weekday_dates_without_trade"] = [str(d.date()) for d in calendar_weekday_month_end() if d not in all_days.index]
        result["alternate_month_end_difference_dates"] = [str(d.date()) for d in LAST if d not in calendar_weekday_month_end()]
        # Year-stratified null: draw the same number of eligible days per year.
        business = all_days.loc[all_days.index.isin(BDAYS)]
        result["permutation"] = {}
        for label, start in [("full", 2006), ("since_2016", 2016), ("since_2025", 2025)]:
            relevant = me[me.year >= start]
            groups = {y: g.pips.to_numpy() for y, g in business[business.year >= start].groupby("year")}
            counts = relevant.groupby("year").size().to_dict()
            null = np.empty(10000)
            for i in range(len(null)):
                samples = [RNG.choice(groups[y], size=n, replace=False) for y, n in counts.items()]
                null[i] = np.concatenate(samples).mean()
            beats = int((null >= relevant.pips.mean()).sum())
            result["permutation"][label] = {"draws": len(null), "beat_or_equal": beats,
                                             "p_plus_one": round(float((beats + 1) / (len(null) + 1)), 5),
                                             "null_mean": round(float(null.mean()), 3),
                                             "null_q95": round(float(np.quantile(null, .95)), 3)}
        result["compound"] = {}
        for label, start in [("since_2016", "2016-01-01"), ("2025_to_2026_09", "2025-01-01")]:
            sub = me[(me.index >= start) & (me.index < END)]
            equity = 1000 * np.cumprod(1 + .02 * sub.pips.to_numpy() / 25)
            result["compound"][label] = {"n": len(sub), "final_eur": round(float(equity[-1]), 2),
                                          "return_pct": round(float((equity[-1] / 1000 - 1) * 100), 2),
                                          "max_drawdown_pct": round(float((equity / np.maximum.accumulate(np.r_[1000, equity])[1:] - 1).min() * 100), 2)}
    return result, me, all_days


def main():
    gbp, _, _ = audit_pair("GBPUSD")
    eur, _, _ = audit_pair("EURUSD")
    out = {"GBPUSD": gbp, "EURUSD": eur}
    (HERE / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    for p, d in out.items():
        print(p, d["main"], "periods", d["periods"])
        print("missing", len(d["missing_month_ends"]), "model spread", d["meta"]["model_spread_pips"])
    print("Wrote results.json")


if __name__ == "__main__":
    main()
