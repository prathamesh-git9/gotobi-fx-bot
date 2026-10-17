"""Published, decades-old market effects, tested with fixed textbook settings (no tuning) and CFD costs.

Daily data: Yahoo Finance (data/daily_yahoo.parquet). Markets Exness offers as CFDs:
  gold (GLD), silver (SLV), S&P 500 (SPY), Nasdaq 100 (QQQ), DAX, FTSE 100, Nikkei 225,
  EURUSD GBPUSD USDJPY AUDUSD USDCAD USDCHF NZDUSD, and Bitcoin (reported separately).

Strategies (settings are the published ones, never optimised here):
  TSMOM   time-series momentum, Moskowitz-Ooi-Pedersen (2012): every month-end go long markets whose
          12-month return is positive, short the rest; each market sized to equal volatility.
  SMA     50/200-day moving-average trend, long/short, same sizing, checked daily.
  TOM     turn of the month, Lakonishok-Smidt (1988) / McConnell-Xu (2008): hold the index from the close
          of the 2nd-last trading day of the month to the close of the 3rd trading day of the next.
  NIGHT   overnight index drift (Cliff-Cooper-Gulen 2008): buy the S&P 500 at the close, sell at the open.

Costs, charged as an Exness Standard CFD account would:
  spread+slippage per side (fraction of price): gold 0.75bp, silver 4bp, indices 2bp, FX 0.6bp, BTC 5bp
  (measured: FX majors ~0.9bp round trip, gold 0.5-1.8bp, US500 ~3.5bp until Exness cut it to ~0.65bp in Sep 2025)
  overnight financing on notional per calendar day: longs pay T-bill + 2.5%/yr, shorts pay 1%/yr
  (FX: 1.5%/yr either side, the carry differential is ignored - conservative for neither side).
"""
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parent.parent / "data"
RES = DATA.parent / "results"
CLASS = {"GLD": "gold", "SLV": "silver", "SPY": "index", "QQQ": "index", "^GDAXI": "index", "^FTSE": "index",
         "^N225": "index", "EURUSD=X": "fx", "GBPUSD=X": "fx", "USDJPY=X": "fx", "AUDUSD=X": "fx",
         "USDCAD=X": "fx", "USDCHF=X": "fx", "NZDUSD=X": "fx", "BTC-USD": "crypto"}
SIDE_COST = {"gold": 0.75e-4, "silver": 4e-4, "index": 2e-4, "fx": 0.6e-4, "crypto": 5e-4}   # measured Exness spreads (half per side) + slippage
EU_LEV = {"gold": 20, "silver": 10, "index": 20, "fx": 30, "crypto": 2}
CORE = [s for s in CLASS if s != "BTC-USD"]


def load():
    d = pd.read_parquet(DATA / "daily_yahoo.parquet")
    d["date"] = pd.to_datetime(d["date"]).dt.tz_localize(None).dt.normalize()
    d = d.drop_duplicates(["sym", "date"], keep="last")
    close = d.pivot(index="date", columns="sym", values="close").sort_index()
    opn = d.pivot(index="date", columns="sym", values="open").sort_index()
    rf = (close["^IRX"].ffill() / 100).clip(lower=0)
    return close, opn, rf


def finance_rate(sym, side, rf):
    """annual financing cost on notional for holding `side` (+1/-1)."""
    if CLASS[sym] == "fx":
        return pd.Series(0.015, index=rf.index)
    if CLASS[sym] == "crypto":
        return pd.Series(0.10, index=rf.index)
    return rf + 0.025 if side > 0 else pd.Series(0.01, index=rf.index)


def trend_book(close, rf, syms, kind, target=0.10):
    """daily portfolio returns of a vol-scaled trend book (TSMOM or SMA) with costs."""
    px = close[syms]
    idx = px.dropna(how="all").index
    px = px.loc[idx]
    ret = px.pct_change(fill_method=None)
    vol = ret.ewm(span=60, min_periods=60).std() * np.sqrt(252)
    if kind == "TSMOM":
        sig = np.sign(px / px.shift(252) - 1)
        month_end = pd.Series(idx.to_period("M"), index=idx)
        rebal = (month_end != month_end.shift(-1)).to_numpy()   # last trading day of each month
    else:
        sig = np.sign(px.rolling(50).mean() - px.rolling(200).mean())
        rebal = np.ones(len(idx), bool)
    n_live = sig.notna().sum(1).clip(lower=1)
    raw = sig * (target / vol).div(np.sqrt(n_live), axis=0)
    if kind == "TSMOM":
        w = raw.where(pd.Series(rebal, index=idx), np.nan).ffill()
    else:   # direction updates daily, size only at month-end (so it trades on flips + monthly resize)
        month_end = pd.Series(idx.to_period("M"), index=idx)
        me = (month_end != month_end.shift(-1))
        size = raw.abs().where(me, np.nan).ffill().fillna(raw.abs())
        w = sig * size
    w = w.fillna(0.0)
    held = w.shift(1).fillna(0.0)                 # decided at today's close, earns tomorrow
    gross = (held * ret.fillna(0.0)).sum(1)
    days = pd.Series(idx, index=idx).diff().dt.days.fillna(1).to_numpy()
    fin = pd.Series(0.0, index=idx)
    trade = pd.Series(0.0, index=idx)
    for s in syms:
        fl = finance_rate(s, 1, rf).reindex(idx).ffill().fillna(0.03)
        fs = finance_rate(s, -1, rf).reindex(idx).ffill().fillna(0.01)
        h = held[s]
        fin += (h.clip(lower=0) * fl + (-h.clip(upper=0)) * fs) * days / 360
        trade += (w[s] - w[s].shift(1).fillna(0)).abs() * SIDE_COST[CLASS[s]]
    net = gross - fin - trade.shift(1).fillna(0)
    # margin used per unit of equity under EU retail leverage caps
    margin = sum(w[s].abs() / EU_LEV[CLASS[s]] for s in syms)
    return pd.DataFrame({"gross": gross, "net": net, "lev": w.abs().sum(1), "margin": margin})


def tom(close, rf, sym):
    px = close[sym].dropna()
    ret = px.pct_change(fill_method=None)
    per = px.index.to_period("M")
    pos_in_month = pd.Series(1, index=px.index).groupby(per).cumsum()
    from_end = pd.Series(1, index=px.index).groupby(per).transform('size') - pos_in_month + 1
    # returns earned on: last trading day (from_end==1) and first three trading days
    hold = ((from_end == 1) | (pos_in_month <= 3)).to_numpy()
    days = pd.Series(px.index, index=px.index).diff().dt.days.fillna(1)
    fin = (rf.reindex(px.index).ffill().fillna(0.03) + 0.025) * days / 360
    entry = (from_end == 2).to_numpy()          # buy at that close
    cost = np.where(entry, 2 * SIDE_COST[CLASS.get(sym, "index")], 0.0)
    gross = pd.Series(np.where(hold, ret, 0.0), index=px.index)
    net = gross - np.where(hold, fin, 0.0) - pd.Series(cost, index=px.index).shift(1).fillna(0)
    return pd.DataFrame({"gross": gross, "net": net, "other": pd.Series(np.where(~hold, ret, 0.0), index=px.index)})


def night(close, opn, rf, sym="SPY"):
    c, o = close[sym].dropna(), opn[sym].dropna()
    on = (o / c.shift(1) - 1).dropna()
    day = (c / o - 1).reindex(on.index)
    days = pd.Series(on.index, index=on.index).diff().dt.days.fillna(1)
    fin = (rf.reindex(on.index).ffill().fillna(0.03) + 0.025) * days / 360
    return pd.DataFrame({"gross": on, "net": on - fin - 2 * SIDE_COST["index"], "intraday": day})


def stats(r, ppy=252):
    r = r.dropna()
    if len(r) < 20:
        return dict(cagr=np.nan, vol=np.nan, sharpe=np.nan, mdd=np.nan)
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    vol = r.std() * np.sqrt(ppy)
    return dict(cagr=eq.iloc[-1] ** (1 / max(yrs, 0.1)) - 1, vol=vol,
                sharpe=r.mean() / r.std() * np.sqrt(ppy) if r.std() > 0 else np.nan,
                mdd=(1 - eq / eq.cummax()).max())


def fmt(s):
    return f"CAGR {s['cagr']:+6.1%}  vol {s['vol']:5.1%}  Sharpe {s['sharpe']:+.2f}  maxDD {s['mdd']:5.1%}"


def periods(r, cuts):
    out = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        x = r[(r.index >= a) & (r.index < b)]
        out.append((f"{a[:4]}-{str(int(b[:4]) - 1)}", stats(x)))
    return out


if __name__ == "__main__":
    close, opn, rf = load()
    books = {}
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p("=== Trend following (vol target 10%/yr, before scaling up) ===")
    for kind in ("TSMOM", "SMA"):
        for label, syms in (("14 CFD markets", CORE), ("+ Bitcoin", CORE + ["BTC-USD"])):
            b = trend_book(close, rf, syms, kind)
            b = b[b.index >= "2005-01-01"]
            books[(kind, label)] = b
            yrs = b.net.groupby(b.index.year).apply(lambda x: (1 + x).prod() - 1)
            p(f"\n{kind} {label}  2005-2026  gross {fmt(stats(b.gross))}")
            p(f"{'':>{len(kind) + len(label) + 13}}net {fmt(stats(b.net))}   years up {np.mean(yrs > 0):.0%}  "
              f"avg margin used {b.margin.mean():.0%} (max {b.margin.max():.0%})")
            for lab, s in periods(b.net, ["2005-01-01", "2012-01-01", "2019-01-01", "2023-10-01", "2026-12-31"]):
                p(f"     {lab}: {fmt(s)}")
            p("     by year: " + " ".join(f"{y % 100:02d}:{v:+.0%}" for y, v in yrs.items()))

    p("\n=== Turn of the month (last day + first 3 days), net of CFD spread + financing ===")
    for sym in ("^GSPC", "SPY", "QQQ", "^GDAXI", "^FTSE", "^N225"):
        t = tom(close, rf, sym)
        days_in = (t.gross != 0).mean()
        p(f"\n{sym}: in the market {days_in:.0%} of days")
        for lab, a, b in (("1950-1989", "1950", "1990"), ("1990-2007 (pre-publication)", "1990", "2008"),
                          ("2008-2026 (post-publication)", "2008", "2027"), ("last 3 years", "2023-10-01", "2027")):
            x = t[(t.index >= a) & (t.index < b)]
            if len(x) < 200:
                continue
            p(f"  {lab:30s} TOM net {fmt(stats(x.net))} | rest of month (gross) CAGR {stats(x.other)['cagr']:+.1%}")
        books[("TOM", sym)] = t

    p("\n=== Overnight S&P 500 (buy close, sell open) ===")
    n = night(close, opn, rf)
    for lab, a, b in (("1993-2007", "1993", "2008"), ("2008-2026", "2008", "2027"), ("last 3 years", "2023-10-01", "2027")):
        x = n[(n.index >= a) & (n.index < b)]
        p(f"  {lab:14s} gross {fmt(stats(x.gross))}\n  {'':14s} net   {fmt(stats(x.net))}  | intraday CAGR {stats(x.intraday)['cagr']:+.1%}")
    pd.to_pickle(books, RES / "classics_books.pkl")
    (RES / "classics_report.txt").write_text("\n".join(lines), encoding="utf-8")
