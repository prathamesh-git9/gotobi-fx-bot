"""Reproduce the preregistered six-idea bid/ask backtest in RULES.md."""
from __future__ import annotations

import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

ROOT = Path(__file__).resolve().parent
DATA = Path(r"E:\Projects\New folder\liquidity_sweep\data")
EXTRA = Path(r"E:\Projects\New folder\liquidity_sweep\strategies\explore\data")
START = pd.Timestamp("2016-10-01")
END = pd.Timestamp("2026-10-01")
SPLIT = pd.Timestamp("2022-01-01")
RECENT = pd.Timestamp("2024-10-01")
COLS = ["Timestamp", "bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]


def load(sym: str) -> pd.DataFrame:
    if sym in ("EURUSD", "USDJPY", "XAUUSD"):
        names = {"XAUUSD": ["XAUUSDm_2015_m1", "XAUUSDm_m1"]}.get(sym, [f"{sym}m_2016_m1", f"{sym}m_m1"])
        frames = [pd.read_parquet(DATA / (n + ".parquet"), columns=COLS).reset_index() for n in names]
        frame = pd.concat(frames, ignore_index=True)
    elif sym in ("US500", "DE30"):
        frame = pd.read_parquet(DATA / (sym + "m_m1.parquet"), columns=COLS).reset_index()
    else:
        frame = pd.read_parquet(EXTRA / (sym + "m_m1.parquet"), columns=COLS).reset_index()
    frame = frame.loc[(frame.Timestamp >= START - pd.Timedelta(days=30)) & (frame.Timestamp < END)].copy()
    frame = frame.sort_values("Timestamp").drop_duplicates("Timestamp").set_index("Timestamp")
    frame["midclose"] = (frame.bclose + frame.aclose) / 2
    return frame


def times(dates, hhmm):
    return pd.DatetimeIndex(dates) + pd.Timedelta(hhmm + ":00")


def quotes(frame, ts, field="midclose", forward=False):
    # A missing timestamp may use only an earlier signal quote or a later fill quote.
    return frame[field].reindex(ts, method="bfill" if forward else "ffill", tolerance=pd.Timedelta(minutes=2)).to_numpy()


def signal_return(frame, dates, t0, t1):
    a = quotes(frame, times(dates, t0))
    b = quotes(frame, times(dates, t1))
    return np.log(b / a)


def weekdays(start=START, end=END):
    return pd.date_range(start, end - pd.Timedelta(days=1), freq="B")


def events(idea, frames):
    dates = weekdays(pd.Timestamp("2019-08-01") if idea in (1, 3) else START)
    if idea == 1:
        r = signal_return(frames["US500"], dates, "14:30", "15:00")
        side = np.where(r >= .0015, 1, np.where(r <= -.0015, -1, 0))
        target, ent, out, stop, pip = "USDJPY", "15:01", "17:00", 25, .01
    elif idea == 2:
        r = signal_return(frames["XAUUSD"], dates, "12:00", "13:00")
        side = np.where(r >= .0020, 1, np.where(r <= -.0020, -1, 0))
        target, ent, out, stop, pip = "AUDUSD", "13:01", "17:00", 20, .0001
    elif idea == 3:
        r = signal_return(frames["US500"], dates, "18:00", "20:00")
        side = np.where(r >= .0025, 1, np.where(r <= -.0025, -1, 0))
        dates = dates + pd.offsets.BDay(1)
        target, ent, out, stop, pip = "DE30", "07:01", "09:00", 100, 1.
    elif idea == 4:
        r = (signal_return(frames["EURUSD"], dates, "08:00", "09:00") +
             signal_return(frames["USDJPY"], dates, "08:00", "09:00") -
             signal_return(frames["EURJPY"], dates, "08:00", "09:00"))
        side = np.where(r >= .0005, 1, np.where(r <= -.0005, -1, 0))
        target, ent, out, stop, pip = "EURJPY", "09:01", "11:00", 25, .01
    elif idea == 5:
        r = signal_return(frames["USDJPY"], dates, "13:00", "14:00")
        side = np.where(r >= .0035, -1, np.where(r <= -.0035, 1, 0))
        target, ent, out, stop, pip = "USDJPY", "14:01", "17:00", 25, .01
    else:
        f = frames["EURUSD"]
        h = f.bhigh.add(f.ahigh).div(2)
        l = f.blow.add(f.alow).div(2)
        window = (f.index.hour >= 8) & (f.index.hour < 17)
        w = pd.DataFrame({"h": h[window], "l": l[window]})
        g = w.groupby(w.index.normalize()).agg({"h": ["max", "count"], "l": "min"})
        rng = (g[("h", "max")] - g[("l", "min")]).where(g[("h", "count")] >= 500)
        rng = rng.dropna()
        med = rng.shift(1).rolling(20, min_periods=20).median()
        prev_ix = rng.index.searchsorted(dates, side="left") - 1
        quiet = np.zeros(len(dates), dtype=bool)
        valid_ix = prev_ix >= 0
        quiet[valid_ix] = (rng.iloc[prev_ix[valid_ix]].to_numpy() <
                           med.iloc[prev_ix[valid_ix]].to_numpy())
        r = signal_return(f, dates, "08:00", "09:00")
        side = np.where(quiet & (r >= .0008), 1, np.where(quiet & (r <= -.0008), -1, 0))
        target, ent, out, stop, pip = "EURUSD", "09:01", "12:00", 20, .0001
    eligible = (side != 0) & np.isfinite(r)
    return pd.DataFrame({"date": dates[eligible], "side": side[eligible], "entry_time": times(dates[eligible], ent),
                         "exit_time": times(dates[eligible], out)}), target, stop, pip


def fills(ev, frame, stop_pips, pip, sides):
    ix = frame.index
    bidopen = frame.bopen.to_numpy(); askopen = frame.aopen.to_numpy()
    bidlow = frame.blow.to_numpy(); askhigh = frame.ahigh.to_numpy()
    entries = ix.searchsorted(ev.entry_time.to_numpy())
    exits = ix.searchsorted(ev.exit_time.to_numpy())
    out = []
    for j, row in enumerate(ev.itertuples(index=False)):
        ei, xi = int(entries[j]), int(exits[j]); s = int(sides[j])
        if ei >= len(ix) or xi >= len(ix) or xi <= ei:
            continue
        if ix[ei] > row.entry_time + pd.Timedelta(minutes=2) or ix[xi] > row.exit_time + pd.Timedelta(minutes=15):
            continue
        emid = (bidopen[ei] + askopen[ei]) / 2
        entry = askopen[ei] if s == 1 else bidopen[ei]
        level = emid - s * stop_pips * pip
        # Check every complete minute bar from entry to before the exit open.
        close = None; stopped = False
        for k in range(ei, xi):
            if s == 1 and bidlow[k] <= level:
                close = min(level, bidopen[k]); stopped = True; break
            if s == -1 and askhigh[k] >= level:
                close = max(level, askopen[k]); stopped = True; break
        if close is None:
            close = bidopen[xi] if s == 1 else askopen[xi]
        net = s * (close - entry) / pip
        spread = (askopen[ei] - bidopen[ei]) / pip
        out.append((row.date, float(net), float(spread), stopped))
    return pd.DataFrame(out, columns=["date", "pips", "spread", "stopped"])


def stats(df, stop, lo, hi):
    d = df.loc[(df.date >= lo) & (df.date < hi)]
    x = d.pips.to_numpy(); n = len(x)
    if n == 0:
        return {"trades": 0, "mean_pips": None, "t": None, "p": None, "win_rate": None,
                "final_eur": 1000., "max_dd_pct": 0.}
    t = float(np.mean(x) / (np.std(x, ddof=1) / np.sqrt(n))) if n > 1 and np.std(x, ddof=1) else None
    p = float(2 * student_t.sf(abs(t), n - 1)) if t is not None else None
    mult = 1 + .02 * x / (stop + d.spread.to_numpy())
    curve = np.r_[1000., 1000. * np.cumprod(mult)]
    dd = np.max(1 - curve / np.maximum.accumulate(curve)) * 100
    return {"trades": n, "mean_pips": float(np.mean(x)), "t": t, "p": p,
            "win_rate": float(np.mean(x > 0) * 100), "final_eur": float(curve[-1]), "max_dd_pct": float(dd),
            "stopped": int(d.stopped.sum()), "mean_spread": float(d.spread.mean())}


def main():
    names = ["US equities lead yen", "Gold leads Australian dollar", "US close leads Germany",
             "Triangular FX delayed adjustment", "Yen post-shock reversal", "Quiet-day FX continuation"]
    needed = {1: ["US500", "USDJPY"], 2: ["XAUUSD", "AUDUSD"], 3: ["US500", "DE30"],
              4: ["EURUSD", "USDJPY", "EURJPY"], 5: ["USDJPY"], 6: ["EURUSD"]}
    rng = np.random.default_rng(20261019)
    result = []
    for idea in range(1, 7):
        print(f"Running {idea}: {names[idea-1]}", flush=True)
        frames = {sym: load(sym) for sym in needed[idea]}
        ev, target, stop, pip = events(idea, frames)
        live = fills(ev, frames[target], stop, pip, ev.side.to_numpy())
        random_sides = rng.choice([-1, 1], size=len(ev))
        control = fills(ev, frames[target], stop, pip, random_sides)
        windows = {"train": (START if idea not in (1, 3) else pd.Timestamp("2019-08-01"), SPLIT),
                   "holdout": (SPLIT, END), "full": (START, END), "recent": (RECENT, END)}
        item = {"idea": idea, "name": names[idea-1], "stop_pips": stop, "pip_size": pip,
                "periods": {k: stats(live, stop, *v) for k, v in windows.items()},
                "random_control": {k: stats(control, stop, *v) for k, v in windows.items()}}
        result.append(item)
        print(json.dumps({"idea": idea, "holdout": item["periods"]["holdout"]}), flush=True)
        del frames, ev, live, control
        gc.collect()
    (ROOT / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
