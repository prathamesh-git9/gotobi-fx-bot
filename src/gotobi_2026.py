"""Gotobi rule on a EUR 1,000 account, 1 Jan 2026 -> 16 Oct 2026 (last data), trade by trade.

As in gotobi.py: buy USD/JPY at 15:55 UTC the day before each gotobi day, sell at the 09:55 JST fix (00:55 UTC),
55-pip stop, real Exness Standard bid/ask + 0.2 bp slippage per side.
Account: EUR-denominated, Exness Standard (lots rounded DOWN to 0.01, minimum 0.01). Position size so a
55-pip stop loses `risk` of equity. JPY profit -> USD at the exit price -> EUR at the live EUR/USD.
Swap (USD/JPY long held over 17:00 New York) is estimated separately: it depends on the broker's rate that day.
Split version: half the risk on the long into the fix, half on a short 09:55 -> 11:00 JST.
"""
import numpy as np
import pandas as pd

import gotobi as G

START, EQ0 = pd.Timestamp("2026-01-01"), 1000.0
CGT, EXEMPT = 0.33, 1270.0


def eurusd_series():
    files = ["EURUSDm_m1.parquet", "EURUSDm_2026_10_m1.parquet"]
    e = pd.concat([pd.read_parquet(G.DATA / f, columns=["bopen", "aopen"]) for f in files]).sort_index()
    e = e[~e.index.duplicated()]
    return ((e.bopen + e.aopen) / 2)


def eur_at(eu, ts):
    i = eu.index.searchsorted(ts, side="right") - 1
    return eu.iloc[max(i, 0)]


def run(trades, risk, eu, with_swap=False, split=False):
    eq, peak, dd, rows = EQ0, EQ0, 0.0, []
    for _, tr in trades.iterrows():
        r_eur = eq * (risk / 2 if split else risk)
        rate_in = eur_at(eu, tr.t_in)
        units = r_eur * rate_in * tr.ent / (G.STOP_PIPS / 100)
        lots = np.floor(units / 100000 / 0.01) * 0.01
        lots = max(lots, 0.01)
        units = lots * 100000
        pips = tr.net + (tr.swap if with_swap else 0.0)
        pnl = units * pips / 100 / tr.ex / eur_at(eu, tr.t_out)
        eq += pnl
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
        rows.append(dict(leg=tr.leg, day=tr.day, t_in=tr.t_in, ent=tr.ent, t_out=tr.t_out, ex=tr.ex, reason=tr.reason,
                         pips=pips, lots=lots, pnl=pnl, bal=eq))
    return pd.DataFrame(rows), dd


if __name__ == "__main__":
    pd.set_option("display.width", 250)
    df = G.load()
    eu = eurusd_series()
    end = df.index[-1].normalize()
    diff = G.rate_series(START - pd.Timedelta(days=5), end + pd.Timedelta(days=5)).to_dict()
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p(f"Data: Exness USD/JPY ticks to {df.index[-1]} UTC. Account EUR 1,000 on 1 Jan 2026, Exness Standard (0.01-lot steps).")
    for jp in (False, True):
        days = G.gotobi_dates(START, end, jp)
        a = G.trades(df, days, "A", diff).assign(leg="long into fix")
        d = G.trades(df, days, "D", diff).assign(leg="short after fix")
        a = a[a.t_out <= df.index[-1]]
        d = d[d.t_out <= df.index[-1]]
        both = pd.concat([a, d]).sort_values("t_in")
        label = "Japanese holidays also moved" if jp else "the rule exactly as given (weekend -> Friday)"
        p(f"\n######## Gotobi dates: {label}: {len(a)} trades so far in 2026")
        p(f"{'version':34s} {'risk':>5} | {'end balance':>11} {'profit':>8} {'return':>7} {'max DD':>6} | {'win':>4} {'PF':>5} "
          f"| {'with est. swap':>14} | after Irish CGT")
        for name, tr, split in (("long into fix only (A)", a, False), ("split: long into fix + short after", both, True)):
            for risk in (0.01, 0.02, 0.05, 0.10):
                res, dd = run(tr, risk, eu, split=split)
                res_s, _ = run(tr, risk, eu, with_swap=True, split=split)
                gain = res.bal.iloc[-1] - EQ0
                after_tax = res.bal.iloc[-1] - CGT * max(0.0, gain - EXEMPT)
                w = res.pnl[res.pnl > 0].sum()
                l = -res.pnl[res.pnl < 0].sum()
                p(f"{name:34s} {risk:5.0%} | EUR {res.bal.iloc[-1]:7,.0f} {gain:+8,.0f} {gain / EQ0:+7.1%} {dd:6.1%} | "
                  f"{np.mean(res.pnl > 0):4.0%} {w / l if l else np.inf:5.2f} | EUR {res_s.bal.iloc[-1]:8,.0f} | EUR {after_tax:,.0f}")
        if not jp:
            res, dd = run(a, 0.01, eu)
            p("\nTrade list - the rule as given, 1% risk per trade (prices are the real Exness fills):")
            p(f"{'#':>2} {'gotobi day':10s} {'buy (UTC)':16s} {'buy':>8} {'sell (UTC)':16s} {'sell':>8} {'pips':>6} {'lots':>5} "
              f"{'P&L EUR':>8} {'balance':>9}")
            for k, r in res.reset_index(drop=True).iterrows():
                p(f"{k + 1:2d} {r.day.date()!s:10s} {r.t_in:%a %d %b %H:%M} {r.ent:8.3f} {r.t_out:%a %d %b %H:%M} {r.ex:8.3f} "
                  f"{r.pips:+6.1f} {r.lots:5.2f} {r.pnl:+8.2f} {r.bal:9.2f}{'  STOP' if r.reason == 'stop' else ''}")
            m = res.groupby(res.day.dt.to_period("M")).pnl.agg(["sum", "count"])
            p("\nMonthly P&L at 1% risk (EUR): " + "  ".join(f"{str(k)[5:]}: {v['sum']:+.0f} ({int(v['count'])})"
                                                         for k, v in m.iterrows()))
            res5, _ = run(a, 0.05, eu)
            m5 = res5.groupby(res5.day.dt.to_period("M")).pnl.sum()
            p("Monthly P&L at 5% risk (EUR): " + "  ".join(f"{str(k)[5:]}: {v:+.0f}" for k, v in m5.items()))
            res.to_csv(G.RES / "gotobi_2026_trades_1pct.csv", index=False)
    (G.RES / "gotobi_2026_report.txt").write_text("\n".join(lines), encoding="utf-8")
