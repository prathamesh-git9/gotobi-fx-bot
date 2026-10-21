"""Time-series momentum (trend following) as published - my quick cross-check of Codex's study in
codex_audit/trend_swapfree. Fixed before running, no tuning:
 signal  = average of the signs of the 1-, 3- and 12-month returns (Hurst, Ooi & Pedersen 2017 style blend of
           Moskowitz, Ooi & Pedersen 2012)
 size    = each market at (12% / sqrt(N)) / its own 60-day volatility, so the portfolio aims at ~12% a year;
           gross exposure capped at 4x
 trading = weekly (Friday close), paying half the spread on every unit traded: FX 0.5 bp (EURUSD) / 0.75 bp
           (other majors), gold and silver 1.5 bp, indices 1.5 bp (roughly Exness 2019-2024 spreads; cheaper now)
 finance = (i) zero swap - Exness swap-free status kept; (ii) 3% a year on gross exposure as a stand-in for swaps
Universe A (Exness lists these as swap-free eligible): EURUSD, GBPUSD, USDJPY, gold (GLD), S&P 500, NASDAQ (QQQ),
DAX, FTSE. Universe B: A + AUDUSD, NZDUSD, USDCAD, USDCHF, silver (SLV). Daily closes from Yahoo.

  python strategies/trend/tsmom.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
A = ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "GLD", "^GSPC", "QQQ", "^GDAXI", "^FTSE"]
B = A + ["AUDUSD=X", "NZDUSD=X", "USDCAD=X", "USDCHF=X", "SLV"]
HALF_SPREAD = {"EURUSD=X": 0.5e-4, "GLD": 1.5e-4, "SLV": 1.5e-4, "^GSPC": 1.5e-4, "QQQ": 1.5e-4, "^GDAXI": 1.5e-4, "^FTSE": 1.5e-4}
WINDOWS = {"2006-2015 (design era)": ("2006-01-01", "2016-01-01"), "2016-2026 (hold-out)": ("2016-01-01", "2026-10-01"),
           "last 10 yrs 2016-10..2026-09": ("2016-10-01", "2026-10-01"), "last 2 yrs 2024-10..2026-09": ("2024-10-01", "2026-10-01"),
           "2026 Jan..Sep": ("2026-01-01", "2026-10-01")}


def prices():
    y = pd.read_parquet(ROOT / "data" / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    p = y.pivot(index="date", columns="sym", values="close").sort_index()
    p.index = pd.to_datetime(p.index)
    return p[p.index >= "2004-01-01"]


def backtest(px, universe, finance, target=0.12, cap=4.0):
    p = px[universe].ffill(limit=3)
    r = p.pct_change(fill_method=None).fillna(0.0).clip(-0.2, 0.2)
    vol = r.ewm(com=60, min_periods=60).std() * np.sqrt(252)
    sig = sum(np.sign(p / p.shift(n) - 1) for n in (21, 63, 252)) / 3
    fridays = p.index.weekday == 4
    n_live = p.notna().sum(axis=1).clip(lower=1)
    w_raw = sig.mul((target / np.sqrt(n_live)), axis=0) / vol
    w_raw = w_raw[fridays].reindex(w_raw.index).ffill().fillna(0.0)
    gross = w_raw.abs().sum(axis=1)
    w = w_raw.div((gross / cap).clip(lower=1.0), axis=0)
    w = w.where(p.notna(), 0.0)
    held = w.shift(1).fillna(0.0)
    cost_rate = pd.Series({c: HALF_SPREAD.get(c, 0.75e-4) for c in universe})
    costs = (w.diff().abs().fillna(0.0) * cost_rate).sum(axis=1)
    fin = held.abs().sum(axis=1) * (finance / 252)
    ret = (held * r).sum(axis=1) - costs - fin
    return ret[ret.index >= "2006-01-01"], held


def describe(ret, a, b):
    x = ret[(ret.index >= a) & (ret.index < b)]
    eq = 1000 * (1 + x).cumprod()
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    yearly = (1 + x).groupby(x.index.year).prod() - 1
    return dict(eur=round(float(eq.iloc[-1])), cagr=round(float((eq.iloc[-1] / 1000) ** (1 / yrs) - 1) * 100, 1),
                sharpe=round(float(x.mean() / x.std() * np.sqrt(252)), 2), dd=round(float((1 - eq / eq.cummax()).max()) * 100, 1),
                worst_year=round(float(yearly.min()) * 100, 1))


def main():
    px = prices()
    print("Time-series momentum, weekly, 12% vol target. EUR 1,000 compounded daily.\n")
    for uname, uni in (("A swap-free-eligible (8 markets)", A), ("B with other FX + silver (13)", B)):
        for fin, fname in ((0.0, "zero swap"), (0.03, "3%/yr financing")):
            ret, held = backtest(px, uni, fin)
            print(f"== {uname}, {fname}: average gross exposure {held.abs().sum(axis=1)[held.index >= '2006'].mean():.1f}x")
            for wn, (a, b) in WINDOWS.items():
                s = describe(ret, a, b)
                print(f"   {wn:30}: EUR 1,000 -> {s['eur']:>6,}  ({s['cagr']:+5.1f}%/yr, Sharpe {s['sharpe']:+.2f}, max drop {s['dd']:4.1f}%, worst year {s['worst_year']:+.1f}%)")
    print("\nBenchmark, equal-weight long-only in universe A at the same 12% vol (zero swap):")
    px2 = px[A].ffill(limit=3)
    r = px2.pct_change(fill_method=None).fillna(0.0).clip(-0.2, 0.2)
    vol = r.ewm(com=60, min_periods=60).std() * np.sqrt(252)
    w = ((0.12 / np.sqrt(len(A))) / vol).shift(1).fillna(0.0)
    long_only = (w * r).sum(axis=1)
    long_only = long_only[long_only.index >= "2006-01-01"]
    for wn, (a, b) in WINDOWS.items():
        s = describe(long_only, a, b)
        print(f"   {wn:30}: EUR 1,000 -> {s['eur']:>6,}  ({s['cagr']:+5.1f}%/yr, Sharpe {s['sharpe']:+.2f}, max drop {s['dd']:4.1f}%)")


if __name__ == "__main__":
    main()
