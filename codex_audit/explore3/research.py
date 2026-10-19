"""Preregistered calendar-flow experiment. See RULES.md before changing anything."""
from __future__ import annotations

import calendar
import json
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import holidays
import numpy as np
import pandas as pd

ROOT = Path(r"E:/Projects/New folder/liquidity_sweep")
DATA = ROOT / "data"
HERE = Path(__file__).resolve().parent
END = date(2026, 9, 30)
HOLDS = (30, 60, 120)

IDEAS = [
    dict(id="US holiday reopening", sym="US500m", country="US", kind="reopen", zone="America/New_York", clock="09:30", side="momentum", stop=30.0, pip=1.0),
    dict(id="German holiday reopening", sym="DE30m", country="DE", kind="reopen", zone="Europe/Berlin", clock="09:00", side="momentum", stop=100.0, pip=1.0),
    dict(id="UK holiday reopening", sym="GBPUSDm", country="GB", kind="reopen", zone="Europe/London", clock="08:00", side="momentum", stop=0.0025, pip=0.0001),
    dict(id="Japan holiday reopening", sym="USDJPYm", country="JP", kind="reopen", zone="Asia/Tokyo", clock="09:00", side="momentum", stop=0.25, pip=0.01),
    dict(id="Quarterly FX futures expiry proxy", sym="EURUSDm", kind="imm", zone="America/New_York", clock="10:00", side="reversal", stop=0.0025, pip=0.0001),
    dict(id="US estimated-tax settlement", sym="US500m", country="US", kind="tax_us", zone="America/New_York", clock="09:30", side="short", stop=30.0, pip=1.0),
    dict(id="UK fiscal-year boundary", sym="GBPUSDm", country="GB", kind="tax_uk", zone="Europe/London", clock="08:00", side="long", stop=0.0025, pip=0.0001),
]


def load_bars(sym: str) -> pd.DataFrame:
    names = [f"{sym}_m1.parquet"]
    if sym in {"EURUSDm", "GBPUSDm", "USDJPYm"}:
        names.insert(0, f"{sym}_2016_m1.parquet")
    cols = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
    frames = [pd.read_parquet(DATA / name, columns=cols) for name in names]
    bars = pd.concat(frames).sort_index()
    bars = bars.loc[~bars.index.duplicated(keep="first")]
    # Vendor timestamps are UTC-naive in the file.
    bars.index = bars.index.tz_localize("UTC")
    return bars.loc[:"2026-10-01"]


def next_workday(d: date, country: str) -> date:
    h = holidays.country_holidays(country, years=range(d.year, d.year + 2))
    d += timedelta(days=1)
    while d.weekday() >= 5 or d in h:
        d += timedelta(days=1)
    return d


def event_dates(idea: dict) -> set[date]:
    kind = idea["kind"]
    out: set[date] = set()
    if kind == "reopen":
        h = holidays.country_holidays(idea["country"], years=range(2015, 2027))
        for d in h:
            if d.weekday() < 5:
                a = next_workday(d, idea["country"])
                if a <= END:
                    out.add(a)
    elif kind == "imm":
        for y in range(2016, 2027):
            for m in (3, 6, 9, 12):
                wednesdays = [d for d in range(1, 22) if date(y, m, d).weekday() == 2]
                out.add(date(y, m, wednesdays[2]))
    elif kind == "tax_us":
        for y in range(2016, 2027):
            for m in (1, 4, 6, 9):
                d = date(y, m, 15)
                h = holidays.country_holidays("US", years=[y])
                while d.weekday() >= 5 or d in h:
                    d += timedelta(days=1)
                out.add(d)
    elif kind == "tax_uk":
        for y in range(2016, 2027):
            d = date(y, 4, 5)
            h = holidays.country_holidays("GB", years=[y])
            while d.weekday() >= 5 or d in h:
                d += timedelta(days=1)
            out.add(d)
    return {d for d in out if d <= END}


def utc_entry(d: date, idea: dict) -> pd.Timestamp:
    local = pd.Timestamp(f"{d.isoformat()} {idea['clock']}", tz=ZoneInfo(idea["zone"]))
    return local.tz_convert("UTC")


def one_trade(bars: pd.DataFrame, when: pd.Timestamp, hold: int, idea: dict):
    start = when - pd.Timedelta(minutes=30)
    stop_at = when + pd.Timedelta(minutes=hold)
    chunk = bars.loc[start:stop_at]
    if len(chunk) != hold + 31 or chunk.index[0] != start or chunk.index[-1] != stop_at:
        return None
    if not (np.diff(chunk.index.as_unit("ns").asi8) == 60_000_000_000).all():
        return None
    a = chunk.iloc[30:30 + hold]
    final = chunk.iloc[-1]
    first = a.iloc[0]
    side = idea["side"]
    if side in {"momentum", "reversal"}:
        pre = ((chunk.iloc[0].bopen + chunk.iloc[0].aopen) -
               (chunk.iloc[29].bclose + chunk.iloc[29].aclose))
        if pre == 0:
            return None
        direction = -1 if pre > 0 else 1  # sign of prior move
        if side == "reversal":
            direction *= -1
    else:
        direction = 1 if side == "long" else -1
    distance = idea["stop"]
    if direction == 1:
        entry = first.aopen
        stop, target = entry - distance, entry + distance
        for row in a.itertuples():
            if row.blow <= stop:  # stop takes precedence
                price = min(stop, row.bopen)
                break
            if row.bhigh >= target:
                price = target
                break
        else:
            price = final.bopen
        net = price - entry
    else:
        entry = first.bopen
        stop, target = entry + distance, entry - distance
        for row in a.itertuples():
            if row.ahigh >= stop:
                price = max(stop, row.aopen)
                break
            if row.alow <= target:
                price = target
                break
        else:
            price = final.aopen
        net = entry - price
    return {"r": float(net / distance), "units": float(net / idea["pip"]), "direction": direction}


def p_signflip(diff: np.ndarray, seed: int) -> float:
    if len(diff) == 0:
        return 1.0
    observed = diff.mean()
    rng = np.random.default_rng(seed)
    exceed = 0
    total = 100_000
    for _ in range(0, total, 2000):
        signs = rng.choice((-1, 1), size=(2000, len(diff)))
        exceed += int(np.count_nonzero((signs * diff).mean(axis=1) >= observed - 1e-12))
    return (exceed + 1) / (total + 1)


def summarize(pairs: list[dict]) -> dict:
    if not pairs:
        return {"n": 0, "event_mean_r": None, "control_mean_r": None, "difference_r": None,
                "event_win_pct": None, "event_net_units": None}
    e = np.array([p["event"]["r"] for p in pairs])
    c = np.array([p["control"]["r"] for p in pairs])
    return {"n": len(pairs), "event_mean_r": float(e.mean()), "control_mean_r": float(c.mean()),
            "difference_r": float((e-c).mean()), "event_win_pct": float(100*(e > 0).mean()),
            "event_net_units": float(sum(p["event"]["units"] for p in pairs))}


def main() -> None:
    results = []
    by_sym = {}
    for i, idea in enumerate(IDEAS):
        sym = idea["sym"]
        if sym not in by_sym:
            by_sym[sym] = load_bars(sym)
        bars = by_sym[sym]
        dates = event_dates(idea)
        candidates = sorted(d for d in dates if d >= date(2016, 1, 10))
        splits = {}
        for hold in HOLDS:
            pairs = []
            for d in candidates:
                control_d = d - timedelta(days=7)
                if control_d in dates:
                    continue
                event = one_trade(bars, utc_entry(d, idea), hold, idea)
                control = one_trade(bars, utc_entry(control_d, idea), hold, idea)
                if event is not None and control is not None:
                    pairs.append({"date": d.isoformat(), "event": event, "control": control})
            splits[hold] = pairs
        train = {h: summarize([p for p in splits[h] if p["date"] < "2022-01-01"]) for h in HOLDS}
        chosen = max(HOLDS, key=lambda h: (train[h]["difference_r"] if train[h]["n"] else -float("inf"), -h))
        all_pairs = splits[chosen]
        test = [p for p in all_pairs if p["date"] >= "2022-01-01"]
        diff = np.array([p["event"]["r"] - p["control"]["r"] for p in test])
        p = p_signflip(diff, 91351+i)
        early = summarize([x for x in test if x["date"] < "2025-01-01"])
        late = summarize([x for x in test if x["date"] >= "2025-01-01"])
        summary = summarize(test)
        survivor = (p*len(IDEAS) < 0.05 and summary["event_mean_r"] is not None and
                    summary["event_mean_r"] > 0 and early["n"] and late["n"] and
                    early["event_mean_r"] > 0 and late["event_mean_r"] > 0)
        item = {"idea": idea["id"], "symbol": sym, "hold": chosen,
                "train": {str(h): train[h] for h in HOLDS}, "test": summary,
                "test_2022_2024": early, "test_2025_2026": late,
                "p_one_sided": p, "p_bonferroni": min(1.0, p*len(IDEAS)),
                "survivor": bool(survivor), "eligible_dates": len(dates)}
        if survivor:
            yearly = {}
            for pair in all_pairs:
                y = pair["date"][:4]
                yearly[y] = yearly.get(y, 0) + pair["event"]["units"]
            def compound(seq):
                equity = 1000.0
                for pair in seq:
                    equity *= 1 + 0.02*pair["event"]["r"]
                return equity
            item["yearly_net_units"] = yearly
            item["equity_from_start"] = compound(all_pairs)
            item["equity_from_2025"] = compound([x for x in all_pairs if x["date"] >= "2025-01-01"])
        results.append(item)
        print(f"{idea['id']}: H={chosen}, train N={train[chosen]['n']}, test N={summary['n']}, diff={summary['difference_r']}, p_adj={item['p_bonferroni']}, survivor={survivor}", flush=True)
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
