"""Round 6 (my half; Codex works the same question independently in codex_audit/smc_research): the PUBLISHED,
research-backed versions of breakouts, support/resistance and order flow. Rules fixed before running, taken from
the papers as literally as our data allows; one version each.

 B1 Opening-range breakout (Zarattini & Aziz 2023, SSRN 4416622, "Can Day Trading Really Be Profitable?"): the
    direction of the first 5-minute candle of the cash session; enter at the open of the second candle; stop at the
    other end of the first candle; target 10R; otherwise out at the close. No trade if the candle closes at its open.
    NASDAQ (USTEC), S&P 500, Dow (09:30 NY), DAX (09:00 Frankfurt).
 B1v "In play" version (their follow-up): B1 only on days when the first 5 minutes had at least 1.5x their usual
    activity (tick count vs the previous 14 days; we have no exchange volume).
 B1f "Order flow confirms": B1 only when the first 5 minutes' tick-rule imbalance (up-ticks minus down-ticks over
    their sum) agrees with the candle and is in its top third (threshold from 2019-2021 only).
 B2 Noise-area intraday momentum (Zarattini, Aziz & Barbon 2024, "Beat the Market"): bands = day's open (gap-
    adjusted with yesterday's close) +- the average absolute move from the open to that minute over the last 14 days;
    every :00 and :30 from 10:00, go long above the upper band / short below the lower band; exit when price crosses
    back over max(upper band, VWAP) (min for shorts); flat at 15:58 NY. Sized to a 2% daily-volatility target, at
    most 4x. VWAP weighted by tick count. S&P 500 and NASDAQ. Benchmark: long 09:30 -> 16:00 every day, same sizing.
 B4 Round numbers (Osler 2003, 2005, NY Fed): stop-losses cluster just beyond round numbers, so a crossing of a
    round number (x.x000 / x.x050; JPY xx.00 / xx.50) should run further than a crossing of an arbitrary level (the
    same grid shifted by 23 or 37 pips). Fresh crossings only (no crossing of that level in the previous hour),
    07:00-20:00 UTC. Trade: enter with the cross at the next minute, stop 10 pips, out after 30 minutes. EURUSD,
    GBPUSD, USDJPY 2016-2026. Placebo = the same rule at the shifted grid.
 B4r Take-profits cluster ON round numbers, so price should bounce there: a fresh approach (no touch in the last
    hour) that comes within 2 pips of a round number without crossing it -> fade at the next minute, stop 10 pips,
    out after 30 minutes. Placebo grid as above.
 B5 Support/resistance breakout: the first M5 close beyond the previous session's high/low in the first part of the
    session (US indices 09:30-12:00 NY, DAX 09:00-12:00 Frankfurt, gold 07:00-16:00 UTC), having opened the window
    inside the range; enter at the next minute in the breakout direction; stop 0.25 x the average daily range of
    the last 14 sessions; target 2R; flat at the session close.
(Gao, Han, Li & Zhou 2018 "market intraday momentum" was already tested here as src/close_mom*.py: dead on US
indices 2024-26.)

Pass for R-based rules: positive in both halves (to 2021 / from 2022), beats the same entries in a random direction,
t > 2.8. For B2: positive in both halves and t of daily returns > 2.8, and beats the benchmark.

  python strategies/breakouts/lab6.py [B1 B2 B4 B5]
"""
import gc
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "different"))
import lab4  # noqa: E402
from lab4 import M, report, run, tstat  # noqa: E402

ROOT = HERE.parents[1]
DATA = ROOT / "data"
UTC, NY, FRA = ZoneInfo("UTC"), ZoneInfo("America/New_York"), ZoneInfo("Europe/Berlin")
B8 = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
lab4.PIP.update({"USTECm": 1.0, "US500m": 0.1, "US30m": 1.0, "DE30m": 0.1, "XAUUSDm": 0.1})
# US exits at 15:58: in 2021-22 (and parts of 2019-20, 2023) Exness's US index quotes stop at 15:59 NY
SESS = {"USTECm": (NY, "09:30", "15:58"), "US500m": (NY, "09:30", "15:58"), "US30m": (NY, "09:30", "15:58"),
        "DE30m": (FRA, "09:00", "17:30")}
OUT = {}


def load(sym, flow=False):
    files = lab4.FILES.get(sym, [sym])
    cols = B8 + (["n", "up", "dn"] if flow else [])
    parts = [pd.read_parquet(DATA / f"{f}_m1.parquet", columns=cols) for f in files if (DATA / f"{f}_m1.parquet").exists()]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    df = df[(df.index >= "2016-01-01") & (df.index < "2026-10-01")]
    return df.astype({c: "float32" for c in cols if c in ("n", "up", "dn")})


def hm(s):
    h, m = map(int, s.split(":"))
    return time(h, m)


def sessions(sym):
    tz, a, b = SESS[sym]
    days = pd.bdate_range("2019-08-05", "2026-09-30")
    return [(d.date(), datetime.combine(d.date(), hm(a), tz), datetime.combine(d.date(), hm(b), tz)) for d in days]


# ------------------------------------------------------------------ B1 opening-range breakout
def B1():
    for sym in ("USTECm", "US500m", "US30m", "DE30m"):
        df = load(sym, flow=True)
        m = M(df, lab4.PIP[sym])
        n, up, dn = df.n.to_numpy(), df.up.to_numpy(), df.dn.to_numpy()
        del df
        gc.collect()
        rows = []
        for d, t0, t1 in sessions(sym):
            i0, i5, j = m.i(t0, tol=1), m.i(t0 + timedelta(minutes=5), tol=1), m.i(t1, tol=5)
            if None in (i0, i5, j) or i5 - i0 != 5:
                continue
            o = (m.aopen[i0] + m.bopen[i0]) / 2
            c = (m.aopen[i5] + m.bopen[i5]) / 2
            if c == o:
                continue
            side = 1 if c > o else -1
            hi = ((m.ahigh[i0:i5] + m.bhigh[i0:i5]) / 2).max()
            lo = ((m.alow[i0:i5] + m.blow[i0:i5]) / 2).min()
            e = m.aopen[i5] if side > 0 else m.bopen[i5]
            stop_d = (e - lo) if side > 0 else (hi - e)
            if stop_d <= 0:
                continue
            ticks = n[i0:i5].sum()
            imb = (up[i0:i5].sum() - dn[i0:i5].sum()) / max(up[i0:i5].sum() + dn[i0:i5].sum(), 1)
            rows.append(dict(d=d, i=i5, j=j, side=side, stop=stop_d, ticks=ticks, imb=imb * side))
        r = pd.DataFrame(rows)
        r["rv"] = r.ticks / r.ticks.shift(1).rolling(14).mean()
        thr = r[r.d < date(2022, 1, 1)].imb.quantile(2 / 3)
        for tag, sel in (("", r), ("v", r[r.rv >= 1.5]), ("f", r[r.imb >= thr])):
            sigs = [(x.i, x.j, x.side, x.stop, 10 * x.stop, 0.0) for x in sel.itertuples()]
            name = {"": "opening-range breakout (Zarattini & Aziz)", "v": "ORB, 'in play' days only (ticks >= 1.5x)",
                    "f": f"ORB, order-flow imbalance agrees (top third, >= {thr:.2f})"}[tag]
            report(f"B1{tag} {sym[:-1]} {name}", *run(m, sigs))
        del m, n, up, dn
        gc.collect()


# ------------------------------------------------------------------ B2 noise-area momentum
def b2_daily(sym):
    """Daily returns of the noise-area strategy and of the intraday-long benchmark (both at the paper's sizing)."""
    df = load(sym, flow=True)
    mid = ((df.bclose + df.aclose) / 2).astype("float64")
    loc = df.index.tz_localize("UTC").tz_convert(NY)
    key = pd.DataFrame({"mid": mid.to_numpy(), "n": df.n.to_numpy(), "bo": df.bopen.to_numpy(), "ao": df.aopen.to_numpy(),
                        "date": loc.date, "mod": loc.hour * 60 + loc.minute})
    del df, mid, loc
    gc.collect()
    key = key[(key["mod"] >= 570) & (key["mod"] <= 958)]          # 09:30 .. 15:58 (quotes stop at 15:59 some years)
    days = []
    for d, g in key.groupby("date"):
        if pd.Timestamp(d).weekday() >= 5:
            continue
        g = g.set_index("mod").reindex(range(570, 959))
        if g.mid.isna().mean() > 0.2 or pd.isna(g.bo.iloc[0]) or pd.isna(g.bo.iloc[-1]):
            continue
        days.append((d, g.ffill()))
    del key
    gc.collect()
    close = np.vstack([g.mid.to_numpy() for _, g in days])            # 389 minutes, 09:30 .. 15:58
    opn = np.array([(g.bo.iloc[0] + g.ao.iloc[0]) / 2 for _, g in days])
    move = np.abs(close / opn[:, None] - 1)
    res, bench = {}, {}
    dret = np.r_[np.nan, close[1:, -1] / close[:-1, -1] - 1]
    for k in range(15, len(days)):
        d, g = days[k]
        sig = move[k - 14:k].mean(axis=0)
        prev_c = close[k - 1, -1]
        ub = max(opn[k], prev_c) * (1 + sig)
        lb = min(opn[k], prev_c) * (1 - sig)
        px = g.mid.to_numpy()
        w = g.n.to_numpy()
        vwap = np.cumsum(px * w) / np.maximum(np.cumsum(w), 1)
        bid, ask = g.bo.to_numpy(), g.ao.to_numpy()
        vol = np.nanstd(dret[k - 14:k], ddof=1)
        lev = min(4.0, 0.02 / vol) if vol > 0 else 1.0
        pos, entry, r = 0, 0.0, 0.0
        for t in list(range(30, 361, 30)) + [388]:            # decisions at 10:00, 10:30, ... 15:30; flat at 15:58
            p = px[t - 1]                                      # last completed minute
            want = pos
            if t == 388:
                want = 0
            elif pos == 0:
                want = 1 if p > ub[t - 1] else -1 if p < lb[t - 1] else 0
            elif pos == 1 and p < max(ub[t - 1], vwap[t - 1]):
                want = -1 if p < lb[t - 1] else 0
            elif pos == -1 and p > min(lb[t - 1], vwap[t - 1]):
                want = 1 if p > ub[t - 1] else 0
            if want != pos:
                if pos:
                    x = bid[t] if pos > 0 else ask[t]
                    r += pos * (x - entry) / entry
                if want:
                    entry = ask[t] if want > 0 else bid[t]
                pos = want
        res[pd.Timestamp(d)] = lev * r
        bench[pd.Timestamp(d)] = lev * (bid[388] - ask[0]) / ask[0]
    return pd.Series(res), pd.Series(bench)


def B2():
    for sym in ("US500m", "USTECm"):
        res, bench = b2_daily(sym)
        for name, s in ((f"B2 {sym[:-1]} noise-area momentum (Zarattini, Aziz & Barbon)", res),
                        (f"B2 {sym[:-1]} benchmark: long 09:30-16:00 every day", bench)):
            OUT[name] = {}
            print(f"\n{name}")
            for lab, a, b in (("since 2019-09", "2019-09-01", "2026-10-01"), ("2019-21", "2019-09-01", "2022-01-01"),
                              ("2022-26", "2022-01-01", "2026-10-01"), ("last 2 yrs", "2024-10-01", "2026-10-01")):
                x = s[(s.index >= a) & (s.index < b)]
                eq = 1000 * (1 + x).cumprod()
                dd = (1 - eq / eq.cummax()).max()
                yrs = len(x) / 252
                cagr = (eq.iloc[-1] / 1000) ** (1 / yrs) - 1
                sh = x.mean() / x.std() * np.sqrt(252)
                traded = (x != 0).mean()
                OUT[name][lab] = dict(days=len(x), traded=round(traded, 2), t=round(tstat(x), 2), sharpe=round(sh, 2),
                                      cagr=round(cagr * 100, 1), eur=round(eq.iloc[-1]), dd=round(dd * 100, 1))
                print(f"   {lab:13}: {len(x):4} days ({traded:.0%} traded)  daily t {tstat(x):5.2f}  Sharpe {sh:5.2f}"
                      f"  {cagr * 100:+6.1f}%/yr  EUR 1,000 -> {eq.iloc[-1]:>8,.0f} (max drop {dd * 100:.0f}%)")
        gc.collect()


# ------------------------------------------------------------------ B4 round numbers (Osler)
def B4():
    for sym in ("EURUSDm", "GBPUSDm", "USDJPYm"):
        df = load(sym)
        m = M(df, lab4.PIP[sym])
        hr = df.index.hour.to_numpy()
        mid = ((df.bclose + df.aclose) / 2).to_numpy()
        hi = ((df.bhigh + df.ahigh) / 2).to_numpy()
        lo = ((df.blow + df.alow) / 2).to_numpy()
        del df
        gc.collect()
        pip = lab4.PIP[sym]
        step = 50 * pip
        for name, off in (("round", 0.0), ("placebo +23", 23 * pip), ("placebo +37", 37 * pip)):
            lvl = np.floor((mid - off) / step)
            cross = np.nonzero(lvl[1:] != lvl[:-1])[0] + 1
            sigs, fades = [], []
            last = {}
            for k in cross:
                if not 7 <= hr[k] < 20 or abs(lvl[k] - lvl[k - 1]) != 1:
                    continue
                side = 1 if lvl[k] > lvl[k - 1] else -1
                L = off + step * max(lvl[k], lvl[k - 1])
                key = round(L / pip)
                if k - last.get(key, -10**9) < 60:
                    last[key] = k
                    continue
                last[key] = k
                if k + 31 < len(m.t) and m.t[k + 31] - m.t[k + 1] <= 40:
                    sigs.append((k + 1, k + 31, side, 10 * pip, None, 0.0))
            # B4r: approach within 2 pips of a level without crossing, fresh (no touch of it in the last hour)
            near_up = off + step * (np.floor((mid - off) / step) + 1)     # the level above
            near_dn = off + step * np.floor((mid - off) / step)           # the level below
            gap_up = (near_up - hi) / pip
            gap_dn = (lo - near_dn) / pip
            seen = {}
            for k in np.nonzero(((gap_up >= 0) & (gap_up <= 2)) | ((gap_dn >= 0) & (gap_dn <= 2)))[0]:
                if not 7 <= hr[k] < 20:
                    continue
                if 0 <= gap_up[k] <= 2:
                    L, side = near_up[k], -1
                else:
                    L, side = near_dn[k], +1
                key = round(L / pip)
                if k - seen.get(key, -10**9) < 60:
                    seen[key] = k
                    continue
                seen[key] = k
                if k + 31 < len(m.t) and m.t[k + 31] - m.t[k + 1] <= 40:
                    fades.append((k + 1, k + 31, side, 10 * pip, None, 0.0))
            report(f"B4 {sym[:-1]} cross of a {name} level -> follow 30 min", *run(m, sigs))
            report(f"B4r {sym[:-1]} near-touch of a {name} level -> fade 30 min", *run(m, fades))
        del m, mid, hi, lo, hr
        gc.collect()


# ------------------------------------------------------------------ B5 prior-session high/low breakout
def B5():
    plan = {"USTECm": (NY, "09:30", "12:00", "15:59"), "US500m": (NY, "09:30", "12:00", "15:59"),
            "DE30m": (FRA, "09:00", "12:00", "17:30"), "XAUUSDm": (UTC, "07:00", "16:00", "20:00")}
    for sym, (tz, w0, w1, close_t) in plan.items():
        df = load(sym)
        m = M(df, lab4.PIP[sym])
        b = lab4.mid_bars(df, "5min")
        del df
        gc.collect()
        loc = b.index.tz_localize("UTC").tz_convert(tz)
        b["date"], b["mod"] = loc.date, loc.hour * 60 + loc.minute
        s0 = 0 if tz is UTC else (hm(SESS[sym][1]).hour * 60 + hm(SESS[sym][1]).minute)
        e0 = 24 * 60 if tz is UTC else (hm(close_t).hour * 60 + hm(close_t).minute)
        sess = b[(b["mod"] > s0) & (b["mod"] <= e0)]
        rng = sess.groupby("date").agg(H=("h", "max"), L=("l", "min"))
        rng["adr"] = (rng.H - rng.L).shift(1).rolling(14).mean()
        rng[["pH", "pL"]] = rng[["H", "L"]].shift(1)
        a0, a1 = hm(w0).hour * 60 + hm(w0).minute, hm(w1).hour * 60 + hm(w1).minute
        sigs = []
        for d, g in sess.groupby("date"):
            if d not in rng.index or pd.isna(rng.at[d, "adr"]) or pd.Timestamp(d).weekday() >= 5:
                continue
            pH, pL, adr = rng.at[d, "pH"], rng.at[d, "pL"], rng.at[d, "adr"]
            win = g[(g["mod"] > a0) & (g["mod"] <= a1)]
            if win.empty or not (pL < win.o.iloc[0] < pH):
                continue
            c = win.c.to_numpy()
            k = next((q for q in range(len(c)) if c[q] > pH or c[q] < pL), None)
            if k is None:
                continue
            side = 1 if c[k] > pH else -1
            t1 = datetime.combine(d, hm(close_t), tz) - timedelta(minutes=5)
            stop_d = 0.25 * adr
            sigs.append((m.i(win.index[k]), m.i(t1, tol=10), side, stop_d, 2 * stop_d, 0.0))
        report(f"B5 {sym[:-1]} prior-session high/low breakout, follow it (2R)", *run(m, sigs))
        del m, b, sess
        gc.collect()


if __name__ == "__main__":
    for k in sys.argv[1:] or ["B1", "B4", "B5", "B2"]:
        globals()[k]()
        gc.collect()
    f = HERE / "lab6_results.json"
    old = json.loads(f.read_text()) if f.exists() else {}
    old.update({r["name"]: r for r in lab4.OUT})
    old.update(OUT)
    f.write_text(json.dumps(old, indent=1, default=str))
