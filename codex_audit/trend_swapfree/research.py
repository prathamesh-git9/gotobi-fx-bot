"""Predeclared swap-free trend test. Run: python research.py"""
from __future__ import annotations

import gc
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = Path(r"E:/Projects/New folder/liquidity_sweep/data")
END = "2026-09-30"
MAP = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "XAUUSD": "GLD", "US500": "^GSPC", "USTEC": "QQQ",
    "DE30": "^GDAXI", "UK100": "^FTSE", "AUDUSD": "AUDUSD=X",
    "NZDUSD": "NZDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
    "XAGUSD": "SLV",
}
A = list(MAP)[:8]
B = list(MAP)
FILES = {
    "EURUSD": ["EURUSDm_2016_m1.parquet", "EURUSDm_m1.parquet"],
    "GBPUSD": ["GBPUSDm_2016_m1.parquet", "GBPUSDm_m1.parquet", "GBPUSDm_2026_m1.parquet"],
    "USDJPY": ["USDJPYm_2016_m1.parquet", "USDJPYm_m1.parquet"],
    "XAUUSD": ["XAUUSDm_2015_m1.parquet", "XAUUSDm_m1.parquet"],
    "US500": ["US500m_m1.parquet"], "USTEC": ["USTECm_m1.parquet"],
    "DE30": ["DE30m_m1.parquet"], "UK100": ["UK100m_m1.parquet"],
}
# Conservative fixed full-spread percentages for five B assets lacking Exness M1 files.
# Exness's web tables currently show typical pips (AUD 0.9, NZD 1.4, CAD 1.4,
# CHF 1.3, XAG 3.0); prices below turn pips into approximate percentages.
B_FIXED = {"AUDUSD": .00013, "NZDUSD": .00025, "USDCAD": .00011,
           "USDCHF": .00017, "XAGUSD": .0015}


def minute_observations():
    yearly = {}
    daily_mid = {}
    coverage = {}
    for sym, files in FILES.items():
        pieces = []
        mids = []
        coverage[sym] = []
        for file in files:
            # One minute parquet in memory at a time, 3 fields only.
            d = pd.read_parquet(DATA / file, columns=["Timestamp", "bclose", "aclose"])
            d = d[(d["bclose"] > 0) & (d["aclose"] >= d["bclose"])]
            d = d.loc[:END]
            if len(d) == 0:
                continue
            coverage[sym].append({"file": file, "first": str(d.index.min()),
                                  "last": str(d.index.max()), "rows": int(len(d))})
            liquid = d.between_time("12:00", "16:00", inclusive="left")
            pct = ((liquid["aclose"] - liquid["bclose"]) /
                   ((liquid["aclose"] + liquid["bclose"]) / 2)).rename("spread")
            pieces.append(pct.groupby(pct.index.year).agg(["median", "count"]))
            # Daily 16:00 UTC proxy midpoint, excluding the thin overnight session.
            mid = ((liquid["aclose"] + liquid["bclose"]) / 2)
            mids.append(mid.resample("D").last().dropna())
            del d, liquid, pct, mid
            gc.collect()
        year_values = {}
        for frame in pieces:
            for year, row in frame.iterrows():
                # If files overlap, later file supersedes only when it has more quotes.
                old = year_values.get(int(year))
                if old is None or row["count"] > old["n"]:
                    year_values[int(year)] = {"pct": float(row["median"]), "n": int(row["count"])}
        yearly[sym] = year_values
        daily_mid[sym] = pd.concat(mids).sort_index().groupby(level=0).last()
        print(f"minute {sym}: {sorted(year_values)}", flush=True)
    return yearly, daily_mid, coverage


def load_closes():
    raw = pd.read_parquet(DATA / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    raw = raw[raw["sym"].isin(MAP.values()) & (raw["date"] <= END)]
    raw = raw.drop_duplicates(["date", "sym"], keep="last")
    wide = raw.pivot(index="date", columns="sym", values="close").rename(columns={v: k for k, v in MAP.items()})
    wide = wide.loc[:, B].sort_index()
    cal = pd.date_range(wide.index.min(), END, freq="B")
    wide = wide.reindex(cal).ffill(limit=3)
    for sym in B:
        last = raw.loc[raw["sym"] == MAP[sym], "date"].max()
        first = raw.loc[raw["sym"] == MAP[sym], "date"].min()
        wide.loc[(wide.index < first) | (wide.index > last), sym] = np.nan
    return wide


def spread_matrix(yearly, index, symbols):
    m = pd.DataFrame(index=index, columns=symbols, dtype=float)
    for sym in symbols:
        if sym in B_FIXED:
            m[sym] = B_FIXED[sym]
            continue
        series = yearly[sym]
        years = sorted(series)
        for y in index.year.unique():
            chosen = y if y in series else min(years, key=lambda z: abs(z-y))
            m.loc[m.index.year == y, sym] = series[chosen]["pct"]
    return m


def targets(closes, symbols):
    p = closes[symbols]
    signal = sum(np.sign(p / p.shift(h) - 1) for h in (21, 63, 252)) / 3
    first_all_ready = signal.notna().all(axis=1).idxmax()
    vol = np.log(p / p.shift(1)).rolling(63, min_periods=63).std() * np.sqrt(252)
    vol = vol.clip(lower=.05)
    eligible = signal.notna() & vol.notna() & p.notna()
    n = eligible.sum(axis=1).replace(0, np.nan)
    w = signal.mul(.12 / np.sqrt(n), axis=0) / vol
    w = w.where(eligible, 0).fillna(0).clip(lower=-.75, upper=.75)
    gross = w.abs().sum(axis=1)
    w = w.mul((2 / gross).clip(upper=1).fillna(1), axis=0)
    # Weekly decision; holidays use last business observation of Friday-ending week.
    decision = pd.Series(p.index.to_period("W-FRI"), index=p.index)
    end_of_week = decision.ne(decision.shift(-1))
    w = w.where(end_of_week, np.nan).ffill().fillna(0)
    w.loc[w.index < first_all_ready] = 0
    return w


def run_case(closes, symbols, spreads, kind, finance):
    if kind == "trend":
        target = targets(closes, symbols)
    else:
        seasoned = closes[symbols].notna()
        target = seasoned.div(seasoned.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
        weeks = pd.Series(closes.index.to_period("W-FRI"), index=closes.index)
        target = target.where(weeks.ne(weeks.shift(-1)), np.nan).ffill().fillna(0)
        first_all_ready = targets(closes, symbols).abs().sum(axis=1).gt(0).idxmax()
        target.loc[target.index < first_all_ready] = 0
    # Mark positions at the most recent available close on exchange holidays.
    p = closes[symbols].ffill().to_numpy(dtype=float)
    t = target.to_numpy(dtype=float)
    s = spreads[symbols].to_numpy(dtype=float)
    weeks = pd.Series(closes.index.to_period("W-FRI"), index=closes.index)
    rebalance = weeks.ne(weeks.shift(-1)).to_numpy(copy=True)
    # No point opening new positions at the terminal close.
    rebalance[-1] = False
    units = np.zeros(len(symbols))
    nav = 1.0
    net = np.zeros(len(p))
    cost_points = 0.0
    finance_points = 0.0
    total_turnover = 0.0
    gross_sum = 0.0
    for i in range(len(p)):
        prev_nav = nav
        prior_price = p[i-1] if i else p[i]
        prior_price = np.nan_to_num(prior_price, nan=0.0)
        price = np.nan_to_num(p[i], nan=0.0)
        nav += float(np.dot(units, price - prior_price))
        gross = float(np.dot(np.abs(units), prior_price))
        funding = gross * (.08 / 252) if finance else 0.0
        nav -= funding
        gross_sum += gross / prev_nav
        finance_points += funding / prev_nav
        if rebalance[i]:
            desired = np.divide(t[i] * nav, price, out=np.zeros(len(symbols)), where=price > 0)
            traded = np.abs(desired - units) * price
            cost = float(np.dot(traded, s[i]))
            nav -= cost
            cost_points += cost / prev_nav
            total_turnover += float(traded.sum() / prev_nav)
            units = desired
        net[i] = nav / prev_nav - 1
    net = pd.Series(net, index=closes.index)
    last_trade = int(np.flatnonzero(rebalance)[-1])
    return net, {"spread_total_return_points": cost_points,
                 "financing_total_return_points": finance_points,
                 "turnover_notional": total_turnover,
                 "mean_gross_leverage": gross_sum / len(p),
                 "latest_executed_rebalance": str(closes.index[last_trade].date()),
                 "latest_target_weights": {s: float(v) for s, v in target.iloc[last_trade].items()}}


def metrics(returns, start, end):
    x = returns.loc[start:end]
    if x.empty:
        return None
    wealth = (1 + x).cumprod()
    years = len(x) / 252
    by_year = (1 + x).groupby(x.index.year).prod() - 1
    return {"first": str(x.index[0].date()), "last": str(x.index[-1].date()),
            "days": len(x), "final_eur": round(1000 * float(wealth.iloc[-1]), 2),
            "annual_return": float(wealth.iloc[-1] ** (1 / years) - 1),
            "sharpe": float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if x.std() > 0 else None,
            "max_drawdown": float((wealth / wealth.cummax() - 1).min()),
            "worst_year": int(by_year.idxmin()), "worst_year_return": float(by_year.min()),
            "calendar_year_returns": {str(k): float(v) for k, v in by_year.items()}}


def signal_check(closes, daily_mid):
    out = {}
    for sym, mid in daily_mid.items():
        if len(mid) < 300:
            continue
        ex = mid.reindex(closes.index).ffill(limit=3)
        ya = closes[sym]
        ex_signal = sum(np.sign(ex / ex.shift(h) - 1) for h in (21, 63, 252))
        ya_signal = sum(np.sign(ya / ya.shift(h) - 1) for h in (21, 63, 252))
        week = pd.Series(closes.index.to_period("W-FRI"), index=closes.index)
        Fridays = week.ne(week.shift(-1)).to_numpy()
        valid = Fridays & ex_signal.notna().to_numpy() & ya_signal.notna().to_numpy()
        same = (np.sign(ex_signal[valid]) == np.sign(ya_signal[valid]))
        out[sym] = {"weeks": int(valid.sum()), "same_direction_fraction": float(same.mean()),
                    "first": str(ex_signal.index[valid][0].date()) if valid.any() else None,
                    "last": str(ex_signal.index[valid][-1].date()) if valid.any() else None}
    return out


def main():
    yearly, daily_mid, coverage = minute_observations()
    closes = load_closes()
    checks = signal_check(closes, daily_mid)
    periods = {"full": (str(closes.index[0].date()), END),
               "design": (str(closes.index[0].date()), "2015-12-31"),
               "holdout": ("2016-01-01", END),
               "ten_year": ("2016-10-01", END),
               "two_year": ("2024-10-01", END),
               "ytd_2026": ("2026-01-01", END)}
    result = {"rules_file": "RULES.md", "data_end": END, "coverage": coverage,
              "yearly_spread_fraction": yearly, "signal_agreement": checks,
              "periods": periods, "cases": {}}
    for name, symbols in (("A12", A), ("B12", B)):
        spreads = spread_matrix(yearly, closes.index, symbols)
        first = str(targets(closes, symbols).abs().sum(axis=1).gt(0).idxmax().date())
        for kind in ("trend", "long"):
            for finance in (False, True):
                case = f"{name}_{kind}_{'swap8' if finance else 'swap0'}"
                ret, extra = run_case(closes, symbols, spreads, kind, finance)
                views = {p: metrics(ret, max(start, first), end) for p, (start, end) in periods.items()}
                result["cases"][case] = {"metrics": views, "diagnostics": extra,
                                         "first_all_markets": first}
                print(case, {p: (round(v["annual_return"], 4) if v else None) for p, v in views.items()}, flush=True)
    result["cases"]["cash"] = {"metrics": {p: metrics(pd.Series(0., index=closes.index), s, e)
                                              for p, (s, e) in periods.items()}}
    trade_date = result["cases"]["A12_trend_swap0"]["diagnostics"]["latest_executed_rebalance"]
    fx_eur = float(daily_mid["EURUSD"].loc[trade_date])
    fx_gbp = float(daily_mid["GBPUSD"].loc[trade_date])
    min_lots = {"EURUSD": .01, "GBPUSD": .01, "USDJPY": .01, "XAUUSD": .01,
                "US500": .14, "USTEC": .05, "DE30": .07, "UK100": .05}
    minimum_eur = {
        "EURUSD": 1000.0, "GBPUSD": 1000 * fx_gbp / fx_eur,
        "USDJPY": 1000 / fx_eur,
        "XAUUSD": float(daily_mid["XAUUSD"].loc[trade_date]) / fx_eur,
        "US500": .14 * float(daily_mid["US500"].loc[trade_date]) / fx_eur,
        "USTEC": .05 * float(daily_mid["USTEC"].loc[trade_date]) / fx_eur,
        "DE30": .07 * float(daily_mid["DE30"].loc[trade_date]),
        "UK100": .05 * float(daily_mid["UK100"].loc[trade_date]) * fx_gbp / fx_eur,
    }
    weights = result["cases"]["A12_trend_swap0"]["diagnostics"]["latest_target_weights"]
    result["standard_lot_check"] = {"date": trade_date, "eurusd": fx_eur,
        "instruments": {sym: {"min_lots": min_lots[sym],
                              "target_eur_notional": round(abs(weights[sym]) * 1000, 2),
                              "minimum_eur_notional": round(minimum_eur[sym], 2),
                              "target_below_minimum": abs(weights[sym]) * 1000 < minimum_eur[sym]}
                        for sym in A}}
    (HERE / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("wrote results.json", flush=True)


if __name__ == "__main__":
    main()
