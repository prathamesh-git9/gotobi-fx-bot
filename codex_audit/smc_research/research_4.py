"""Reproduce the four-rule RULES_4.md study: python research_4.py.

Requires pandas, numpy, scipy, pyarrow. Read-only source data live in ../.. /data.
"""
from __future__ import annotations

import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t


HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "data"
SYMBOLS = {
    "XAUUSDm": ["XAUUSDm_2015_m1", "XAUUSDm_m1"],
    "USTECm": ["USTECm_m1"],
    "US500m": ["US500m_m1"],
    "EURUSDm": ["EURUSDm_2016_m1", "EURUSDm_m1"],
    "GBPUSDm": ["GBPUSDm_2016_m1", "GBPUSDm_m1"],
}
RULES = ("PD-break", "PD-retest", "Channel-break", "BOS-FVG-retest")
START = pd.Timestamp("2016-10-01")
END = pd.Timestamp("2026-10-01")
RECENT = pd.Timestamp("2024-10-01")
HOLDOUT = pd.Timestamp("2022-01-01")


def load_symbol(names):
    chunks = []
    cols = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
    for name in names:
        frame = pd.read_parquet(DATA / f"{name}.parquet", columns=cols)
        frame = frame.loc[(frame.index >= START) & (frame.index < END)]
        chunks.append(frame.astype("float64"))
    m1 = pd.concat(chunks).sort_index()
    del chunks, frame
    m1 = m1.loc[~m1.index.duplicated(keep="last")]
    m15 = m1.resample("15min", label="right", closed="left").agg(
        {"bopen": "first", "bhigh": "max", "blow": "min", "bclose": "last"}
    )
    counts = m1.bclose.resample("15min", label="right", closed="left").count()
    m15 = m15.loc[counts == 15].copy()
    m15.columns = ["open", "high", "low", "close"]
    del counts
    gc.collect()
    return m1, m15


def candidates(m15):
    h, l, c, o = (m15[k].to_numpy() for k in ("high", "low", "close", "open"))
    n = len(m15)
    idx = m15.index
    ranges = h - l
    med = pd.Series(ranges).rolling(20, min_periods=20).median().shift(1).to_numpy()
    # Prior UTC calendar day, not merely preceding trading date.
    days = idx.normalize()
    day_stats = m15.groupby(days).agg({"high": "max", "low": "min", "close": "count"})
    prev = day_stats.reindex(days - pd.Timedelta(days=1))
    prev_high = prev.high.to_numpy()
    prev_low = prev.low.to_numpy()
    valid_day = prev.close.to_numpy() >= 40
    ch_high = pd.Series(h).rolling(16, min_periods=16).max().shift(1).to_numpy()
    ch_low = pd.Series(l).rolling(16, min_periods=16).min().shift(1).to_numpy()
    bos_high = pd.Series(h).rolling(16, min_periods=16).max().shift(3).to_numpy()
    bos_low = pd.Series(l).rolling(16, min_periods=16).min().shift(3).to_numpy()
    out = {r: [] for r in RULES}
    pending_pd = None
    pending_fvg = None
    for i in range(50, n):
        ts = idx[i]
        if ts < START or ts >= END or ts.weekday() > 4:
            continue
        hour = ts.hour + ts.minute / 60
        active = 7 <= hour < 18
        if not np.isfinite(med[i]) or ranges[i] <= 0:
            continue

        # Pending setups are examined before a fresh setup on this bar.
        if pending_pd is not None:
            side, level, expiry = pending_pd
            if i > expiry:
                pending_pd = None
            elif active and ((side == 1 and l[i] <= level < c[i]) or
                             (side == -1 and h[i] >= level > c[i])):
                stop = l[i] if side == 1 else h[i]
                out["PD-retest"].append((ts, side, stop, med[i]))
                pending_pd = None
        if pending_fvg is not None:
            side, mid, expiry = pending_fvg
            if i > expiry:
                pending_fvg = None
            elif active and ((side == 1 and l[i] <= mid < c[i]) or
                             (side == -1 and h[i] >= mid > c[i])):
                stop = l[i] if side == 1 else h[i]
                out["BOS-FVG-retest"].append((ts, side, stop, med[i]))
                pending_fvg = None
        if not active:
            continue

        upper_quarter = c[i] >= l[i] + 0.75 * ranges[i]
        lower_quarter = c[i] <= l[i] + 0.25 * ranges[i]
        if valid_day[i]:
            if c[i] > prev_high[i] and c[i-1] <= prev_high[i] and upper_quarter:
                out["PD-break"].append((ts, 1, prev_high[i], med[i]))
                if pending_pd is None:
                    pending_pd = (1, prev_high[i], i + 4)
            elif c[i] < prev_low[i] and c[i-1] >= prev_low[i] and lower_quarter:
                out["PD-break"].append((ts, -1, prev_low[i], med[i]))
                if pending_pd is None:
                    pending_pd = (-1, prev_low[i], i + 4)

        if c[i] > ch_high[i] and c[i-1] <= ch_high[i] and c[i] > c[i-48]:
            out["Channel-break"].append((ts, 1, ch_high[i], med[i]))
        elif c[i] < ch_low[i] and c[i-1] >= ch_low[i] and c[i] < c[i-48]:
            out["Channel-break"].append((ts, -1, ch_low[i], med[i]))

        strong_body = abs(c[i] - o[i]) >= 0.6 * ranges[i]
        if strong_body and pending_fvg is None:
            if h[i-2] < l[i] and c[i] > bos_high[i] and upper_quarter:
                pending_fvg = (1, (h[i-2] + l[i]) / 2, i + 4)
            elif l[i-2] > h[i] and c[i] < bos_low[i] and lower_quarter:
                pending_fvg = (-1, (l[i-2] + h[i]) / 2, i + 4)
    return out


def simulate_one(ts, side, stop, median_range, bars, actual=True):
    times, bo, bh, bl, bc, ao, ah, al, ac = bars
    k = int(np.searchsorted(times, np.datetime64(ts), side="left"))
    if k >= len(times) or times[k] - np.datetime64(ts) > np.timedelta64(2, "m"):
        return None
    entry = ao[k] if side == 1 else bo[k]
    spread = ao[k] - bo[k]
    if actual:
        risk = side * (entry - stop)
    else:
        risk = stop  # caller passes the matched actual risk for a random direction
        stop = entry - side * risk
    if not np.isfinite(risk) or risk <= 0 or risk < 3 * spread or risk > 2 * median_range:
        return None
    target = entry + side * 2 * risk
    deadline = min(pd.Timestamp(times[k]) + pd.Timedelta(hours=4),
                   pd.Timestamp(times[k]).normalize() + pd.Timedelta(hours=20))
    z = min(int(np.searchsorted(times, np.datetime64(deadline), side="left")), len(times)-1)
    # If no quote is present at the cutoff, settle on last available pre-cutoff close.
    missing_cutoff_quote = pd.Timestamp(times[z]).date() != pd.Timestamp(times[k]).date()
    if missing_cutoff_quote:
        z -= 1
    for j in range(k, z):
        if side == 1:
            if bo[j] <= stop:
                return (times[k], times[j], (bo[j]-entry)/risk, risk)
            if bo[j] >= target:
                return (times[k], times[j], (target-entry)/risk, risk)
            if bl[j] <= stop:  # stop wins if both touch
                return (times[k], times[j], (stop-entry)/risk, risk)
            if bh[j] >= target:
                return (times[k], times[j], (target-entry)/risk, risk)
        else:
            if ao[j] >= stop:
                return (times[k], times[j], (entry-ao[j])/risk, risk)
            if ao[j] <= target:
                return (times[k], times[j], (entry-target)/risk, risk)
            if ah[j] >= stop:
                return (times[k], times[j], (entry-stop)/risk, risk)
            if al[j] <= target:
                return (times[k], times[j], (entry-target)/risk, risk)
    if z >= k and missing_cutoff_quote:
        px = bc[z] if side == 1 else ac[z]
        return (times[k], times[z], side*(px-entry)/risk, risk)
    if z >= k and pd.Timestamp(times[z]) <= deadline:
        px = bo[z] if side == 1 else ao[z]
        return (times[k], times[z], side*(px-entry)/risk, risk)
    j = max(k, z-1)
    px = bc[j] if side == 1 else ac[j]
    return (times[k], times[j], side*(px-entry)/risk, risk)


def trade_rule(symbol, rule, signals, m1, seed):
    arrays = tuple(np.ascontiguousarray(x) for x in
                   (m1.index.to_numpy(), *(m1[c].to_numpy() for c in
                     ("bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"))))
    rng = np.random.default_rng(seed)
    trades, random_trades = [], []
    busy_until = np.datetime64("1900-01-01")
    for ts, side, stop, median_range in signals:
        if np.datetime64(ts) <= busy_until:
            continue
        got = simulate_one(ts, side, stop, median_range, arrays)
        if got is None:
            continue
        entry_time, exit_time, r, risk = got
        trades.append({"symbol": symbol, "entry": str(entry_time), "exit": str(exit_time), "r": float(r)})
        busy_until = exit_time
        rand_side = int(rng.choice([-1, 1]))
        baseline = simulate_one(ts, rand_side, risk, median_range, arrays, actual=False)
        if baseline is None:
            raise RuntimeError("A matched random-direction trade was unexpectedly rejected")
        rt, rx, rr, _ = baseline
        random_trades.append({"symbol": symbol, "entry": str(rt), "exit": str(rx), "r": float(rr)})
    return trades, random_trades


def summary(trades, start, end, infer=False):
    subset = sorted((x for x in trades if start <= x["entry"] < end), key=lambda x: x["entry"])
    vals = np.array([x["r"] for x in subset], dtype=float)
    n = len(vals)
    if n == 0:
        return {"trades": 0, "average_r": None, "t": None, "win_rate": None,
                "final_eur": 1000.0, "max_drawdown": 0.0}
    equity = 1000.0
    peak = equity
    max_dd = 0.0
    for r in vals:
        equity *= max(0.0, 1 + 0.02*r)
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak-equity)/peak)
    tstat = float(vals.mean() / (vals.std(ddof=1)/np.sqrt(n))) if n > 1 and vals.std(ddof=1) > 0 else None
    ans = {"trades": n, "average_r": float(vals.mean()), "t": tstat,
           "win_rate": float(np.mean(vals > 0)), "final_eur": float(equity),
           "max_drawdown": float(max_dd)}
    if infer:
        p = float(student_t.sf(tstat, n-1)) if tstat is not None else None
        ans["one_sided_p"] = p
        ans["bonferroni_p"] = min(1.0, 4*p) if p is not None else None
        ans["passes"] = bool(p is not None and vals.mean() > 0 and 4*p < 0.05)
    return ans


def main():
    all_trades = {r: [] for r in RULES}
    all_random = {r: [] for r in RULES}
    coverage = {}
    for symbol, files in SYMBOLS.items():
        print("Processing", symbol, flush=True)
        m1, m15 = load_symbol(files)
        coverage[symbol] = {"first": str(m1.index.min()), "last": str(m1.index.max()),
                            "m1_rows": len(m1), "complete_m15": len(m15)}
        sig = candidates(m15)
        del m15
        gc.collect()
        for ri, rule in enumerate(RULES):
            trades, baseline = trade_rule(symbol, rule, sig[rule], m1, 20261020 + ri*100 + list(SYMBOLS).index(symbol))
            all_trades[rule].extend(trades)
            all_random[rule].extend(baseline)
            print(" ", rule, len(trades), "baseline", len(baseline), flush=True)
        del m1, sig
        gc.collect()
    windows = {"full": ("2016-10-01", "2026-10-01"),
               "recent": ("2024-10-01", "2026-10-01"),
               "holdout": ("2022-01-01", "2026-10-01")}
    results = {"rules_frozen_before_returns": True, "source_data": str(DATA),
               "coverage": coverage, "bonferroni_tests": 4, "windows": windows, "rules": {}}
    for rule in RULES:
        d = {}
        for label, (start, end) in windows.items():
            d[label] = summary(all_trades[rule], start, end, infer=(label == "holdout"))
            d[label]["random_direction"] = summary(all_random[rule], start, end)
            d[label]["beats_random_average_r"] = (d[label]["average_r"] is not None and
                  d[label]["random_direction"]["average_r"] is not None and
                  d[label]["average_r"] > d[label]["random_direction"]["average_r"])
        d["by_symbol_holdout"] = {s: summary([x for x in all_trades[rule] if x["symbol"] == s],
                                              "2022-01-01", "2026-10-01") for s in SYMBOLS}
        results["rules"][rule] = d
    (HERE / "results_4.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print("Wrote results_4.json", flush=True)


if __name__ == "__main__":
    main()
