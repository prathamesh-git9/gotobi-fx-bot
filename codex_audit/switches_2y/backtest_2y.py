"""Independent, reproducible USD/JPY Gotobi backtest using only the two task price files.

Run: python backtest_2y.py
The account is reported as EUR 1,000 of USD-equivalent buying power because no
EUR/JPY or EUR/USD history was supplied. One standard lot is 100,000 USD.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import date, timedelta
from math import floor
from pathlib import Path

import holidays
import numpy as np
import pandas as pd


DATA = Path("E:/Projects/New folder/liquidity_sweep/data")
FILES = (DATA / "USDJPYm_m1.parquet", DATA / "USDJPYm_2026_10_m1.parquet")
PIP = 0.01
START = date(2019, 1, 1)
SPLIT = date(2024, 10, 17)
END = date(2026, 10, 16)


@dataclass(frozen=True)
class Settings:
    risk: float = 0.06
    stop: float = 55.0
    target: float | None = 30.0
    long: bool = True
    short: bool = True
    kill: bool = True
    spread_limit: float = 5.0
    filter_name: str = "none"


def load_prices() -> pd.DataFrame:
    columns = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
    frames = [pd.read_parquet(p, columns=columns) for p in FILES]
    frame = pd.concat(frames).sort_index()
    if frame.index.has_duplicates:
        raise ValueError("Duplicate minute timestamps")
    if not frame.index.is_monotonic_increasing:
        raise ValueError("Unsorted timestamps")
    if frame[columns].isna().any().any():
        raise ValueError("Missing bid/ask values")
    return frame


def schedule() -> list[tuple[date, date]]:
    jp = holidays.Japan(years=range(2018, 2028))
    result = {}
    day = date(2019, 1, 1)
    while day <= END:
        for n in (5, 10, 15, 20, 25, 30):
            try:
                nominal = day.replace(day=n)
            except ValueError:
                continue
            if nominal.month != day.month or nominal.year != day.year:
                continue
            moved = nominal
            while moved.weekday() >= 5 or moved in jp or (moved.month == 12 and moved.day == 31) or (moved.month == 1 and moved.day in (1, 2, 3)):
                moved -= timedelta(days=1)
            if (moved.month, moved.day) in ((12, 25), (1, 1)):
                continue
            if START <= moved <= END:
                result.setdefault(moved, nominal)
        day = (day.replace(day=1) + timedelta(days=32)).replace(day=1)
    return sorted(result.items())


def bar_index(idx: pd.DatetimeIndex, when: pd.Timestamp) -> int | None:
    pos = int(idx.searchsorted(when))
    return pos if pos < len(idx) and idx[pos] == when else None


def build_events(frame: pd.DataFrame) -> list[dict]:
    idx = frame.index
    events = []
    daily = frame["bclose"].resample("D").last().dropna()
    daily_dates = daily.index.date
    daily_vals = daily.to_numpy()
    for moved, nominal in schedule():
        previous = moved - timedelta(days=1)
        if previous.weekday() == 6:
            left = int(idx.searchsorted(pd.Timestamp(previous)))
            right = int(idx.searchsorted(pd.Timestamp(previous + timedelta(days=1))))
            entry = bar_index(idx, idx[left] + pd.Timedelta(minutes=15)) if left < right else None
        else:
            entry = bar_index(idx, pd.Timestamp(previous) + pd.Timedelta(hours=15, minutes=55))
        long_end = bar_index(idx, pd.Timestamp(moved) + pd.Timedelta(minutes=54))
        short_entry = bar_index(idx, pd.Timestamp(moved) + pd.Timedelta(minutes=55))
        short_end = bar_index(idx, pd.Timestamp(moved) + pd.Timedelta(hours=1, minutes=25))
        # Signal uses only completed daily closes available before each entry.
        def signal(cutoff: date) -> int:
            k = int(np.searchsorted(daily_dates, cutoff))
            if k < 20:
                return 0
            return 1 if daily_vals[k - 1] > daily_vals[k - 20:k].mean() else -1
        events.append(dict(day=moved, nominal=nominal, long_entry=entry, long_end=long_end,
                           short_entry=short_entry, short_end=short_end,
                           long_trend=signal(previous), short_trend=signal(moved)))
    return events


def allowed(event: dict, side: str, settings: Settings) -> bool:
    name = settings.filter_name
    if name == "omit_shifted" and event["day"] != event["nominal"]:
        return False
    if name == "omit_30th" and event["nominal"].day == 30:
        return False
    if name == "omit_monday" and event["day"].weekday() == 0:
        return False
    if name == "trend_aligned":
        return event[f"{side}_trend"] == (1 if side == "long" else -1)
    return True


def simulate(frame: pd.DataFrame, events: list[dict], settings: Settings,
             start: date, end: date) -> dict:
    prices = {c: frame[c].to_numpy() for c in frame.columns}
    idx = frame.index
    equity = peak = 1000.0
    max_dd = 0.0
    long_r = deque(maxlen=60)
    rows = []
    skipped = {"missing": 0, "spread": 0, "size": 0, "filter": 0}
    kill_reason = None
    for event in events:
        if not start <= event["day"] <= end:
            continue
        for side in ("long", "short"):
            if not getattr(settings, side):
                continue
            if settings.kill and kill_reason:
                continue
            if not allowed(event, side, settings):
                skipped["filter"] += 1
                continue
            a = event[f"{side}_entry"]
            b = event[f"{side}_end"]
            if a is None or b is None or b <= a:
                skipped["missing"] += 1
                continue
            spread = (prices["aopen"][a] - prices["bopen"][a]) / PIP
            if spread > settings.spread_limit:
                skipped["spread"] += 1
                continue
            entry = prices["aopen"][a] if side == "long" else prices["bopen"][a]
            # Quote-currency risk translated at the entry USD/JPY quote.
            lots = floor((equity * settings.risk * entry / (settings.stop * PIP * 100000) + 1e-12) * 100) / 100
            if lots < 0.01:
                skipped["size"] += 1
                continue
            exit_price = prices["bopen"][b] if side == "long" else prices["aopen"][b]
            exit_pos = b
            reason = "time"
            for i in range(a, b):
                if side == "long":
                    stop_price = entry - settings.stop * PIP
                    tp_price = None if settings.target is None else entry + settings.target * PIP
                    # A gap through a level fills at the first available open.
                    if prices["bopen"][i] <= stop_price:
                        exit_price, reason = prices["bopen"][i], "stop_gap"
                    elif prices["blow"][i] <= stop_price:
                        exit_price, reason = stop_price, "stop"
                    elif tp_price is not None and prices["bopen"][i] >= tp_price:
                        exit_price, reason = prices["bopen"][i], "target_gap"
                    elif tp_price is not None and prices["bhigh"][i] >= tp_price:
                        exit_price, reason = tp_price, "target"
                else:
                    stop_price = entry + settings.stop * PIP
                    if prices["aopen"][i] >= stop_price:
                        exit_price, reason = prices["aopen"][i], "stop_gap"
                    elif prices["ahigh"][i] >= stop_price:
                        exit_price, reason = stop_price, "stop"
                if reason != "time":
                    exit_pos = i
                    break
            pips = (exit_price - entry) / PIP * (1 if side == "long" else -1)
            pnl = pips * PIP * 100000 * lots / exit_price
            equity += pnl
            peak = max(peak, equity)
            max_dd = max(max_dd, 1 - equity / peak)
            r = pips / settings.stop
            rows.append(dict(day=event["day"], side=side, entry_time=idx[a], exit_time=idx[exit_pos],
                             pips=pips, pnl=pnl, r=r, lots=lots, equity=equity, reason=reason))
            if side == "long":
                long_r.append(r)
            if settings.kill:
                if len(long_r) == 60 and sum(long_r) < -6:
                    kill_reason = "last 60 longs below -6R"
                elif equity <= peak * 0.5:
                    kill_reason = "50% equity drawdown"
    trades = pd.DataFrame(rows)
    if len(trades):
        monthly = trades.groupby(pd.to_datetime(trades["exit_time"]).dt.to_period("M"))["pnl"].sum()
        worst_month = str(monthly.idxmin())
        worst_pnl = float(monthly.min())
    else:
        worst_month, worst_pnl = None, 0.0
    return dict(final=equity, dd=max_dd, n=len(trades),
                pips=float(trades.pips.mean()) if len(trades) else 0.0,
                win=float((trades.pnl > 0).mean()) if len(trades) else 0.0,
                worst_month=worst_month, worst_pnl=worst_pnl,
                kill=kill_reason, skipped=skipped, trades=trades)


def main() -> None:
    frame = load_prices()
    events = build_events(frame)
    base = Settings()
    variants = {"Base 6%": base,
                "Risk 2%": replace(base, risk=.02),
                "Risk 4%": replace(base, risk=.04),
                "Risk 8%": replace(base, risk=.08),
                "Risk 10%": replace(base, risk=.10),
                "No take profit": replace(base, target=None),
                "Take profit 20": replace(base, target=20),
                "Take profit 50": replace(base, target=50),
                "Stop 35": replace(base, stop=35),
                "Stop 75": replace(base, stop=75),
                "Long only": replace(base, short=False),
                "Short only": replace(base, long=False),
                "No kill switch": replace(base, kill=False),
                "Spread <=2": replace(base, spread_limit=2),
                "Omit shifted days": replace(base, filter_name="omit_shifted"),
                "Omit nominal 30th": replace(base, filter_name="omit_30th"),
                "Omit Mondays": replace(base, filter_name="omit_monday"),
                "Trend aligned": replace(base, filter_name="trend_aligned")}
    results = {}
    for name, settings in variants.items():
        for period in ("test", "prior"):
            start, end = (SPLIT, END) if period == "test" else (START, SPLIT - timedelta(days=1))
            results[(name, period)] = simulate(frame, events, settings, start, end)
    print("name | period | final | max_dd_pct | trades | win_pct | pips_trade | worst_month | worst_pnl | kill")
    for (name, period), r in results.items():
        print(f"{name} | {period} | {r['final']:.2f} | {100*r['dd']:.2f} | {r['n']} | "
              f"{100*r['win']:.2f} | {r['pips']:.2f} | {r['worst_month']} | {r['worst_pnl']:.2f} | {r['kill']}")
    for period in ("test", "prior"):
        r = results[("Base 6%", period)]
        for side in ("long", "short"):
            t = r["trades"]
            s = t[t.side == side] if len(t) else t
            print(f"{period} {side}: n={len(s)} win={100*(s.pnl>0).mean() if len(s) else 0:.2f}% "
                  f"pips={s.pips.mean() if len(s) else 0:.2f}; skipped={r['skipped']}")


if __name__ == "__main__":
    main()
