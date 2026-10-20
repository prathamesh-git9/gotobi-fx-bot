"""Round 4: "something different" (not calendar flows). The ideas are the ones Gemini 3.1 Pro and Qwen suggested
when asked on 19-20 Oct 2026 (their answers are in ideas.md); the rules below were written BEFORE any return was
computed, taking each model's rule as literally as possible and filling gaps (marked "my choice") once, up front.

 Q1 EURGBP H1 z-score: z of the H1 close vs its 20-bar mean/sd. Enter on the H1 close where z crosses +-2.0 (fade),
    signals closing 07:00-16:00 UTC only, exit at the first H1 close with z back through 0, stop at the price where
    z = +-3.5 at entry (mean +- 3.5 sd), max hold 48 h (my choice). One position at a time.
 G4 AUDNZD H1 z-score: same machinery, enter +-2.5, stop +-4, any hour except 20:00-23:59 UTC (rollover, my choice).
 Q2 USDCNH leads AUDUSD: on an H1 close (01:00-08:00 UTC) where USDCNH closes at its lowest of the last 20 H1 closes
    while AUDUSD is not at its 20-bar high, buy AUDUSD 15 min later (mirror for shorts); TP 0.25%, stop 0.15%,
    exit 3 h after entry.
 Q3 GBPUSD London-morning fade: if GBPUSD moved more than 0.25% from 07:00 to 09:00 UTC, fade it at 09:00, exit
    12:00 UTC, stop 0.15%.
 Q4 Gold refuses to fall: on an H1 bar closing 13:00-16:00 UTC where the USDJPY high is above the highs of the
    previous 20 hours but XAUUSD closed the hour at or above its open, buy XAUUSD; TP 0.25%, stop 0.20%, exit 2 h.
 Q5 US30/USTEC ratio: z of the US30/USTEC ratio of 16:00 NY closes over the previous 20 days; if z > 2 buy USTEC,
    if z < -2 buy US30 at 09:30 NY; TP 0.4%, stop 0.25%, exit 15:00 NY. (2019-08+ data.)
 G3 US500 RSI(2) dip: S&P 500 closed above its 200-day average yesterday (daily ^GSPC); an M15 close between 09:45 and
    16:00 NY with RSI(2) < 10 -> buy at once; exit at the first M15 close with RSI(2) > 70; stop 3 x ATR(14, M15).
    Nights held pay financing at (3-month T-bill + 2.5%)/360 of the price (my assumption of Exness's CFD rate).
 G2 VIX-gated carry: long USDJPY at 22:15 UTC when the VIX closed below 20 and USDJPY is above its 100-day EMA
    (daily series sampled at 22:15 UTC); exit at 22:15 when VIX > 22 or the close is below the EMA; trailing stop
    2.5 x ATR(14) under the highest close since entry, checked on minute lows. Carry per night = (T-bill - BoJ rate -
    1% broker markup)/360. Control: the same trade without the VIX filter.
 G5 Volume-climax fade: an M5 close outside Bollinger(20, 2.5) with tick count > 3x its previous 50-bar average ->
    fade at the next minute; exit at the first M5 close back through the middle band, stop 1.5 x the signal bar's
    range beyond entry, max hold 2 h (my choice); no signals 20:55-23:00 UTC. GBPUSD and XAUUSD.
 G1 US data-surprise drift: on NFP days (third Friday after the reference week; if the 08:30-08:45 NY range is not
    2x its usual size the next Friday is tried), follow the 08:30-08:45 NY move at 08:45, exit 20:55 UTC, stop beyond
    the 15-min candle's far end. EURUSD and USDJPY.

Judgement (same bar as before, made stricter for 13 tests): both 2016-21 and 2022-26 positive, beats the same
entries with a random direction (seeded), and t > 2.8 over the 10 years (Bonferroni, 13 tests, p < 0.005).
Reported for (a) 2016-10-01..2026-09-30 and (b) 2024-10-01..2026-09-30: trades, pips, R, t, win %, EUR 1,000 at 2%
risk per trade compounded (final, max drawdown).

  python strategies/different/lab4.py [Q1 G4 ...]
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
ROOT = HERE.parents[1]
EXPLORE = ROOT / "strategies" / "explore" / "data"
DATA = ROOT / "data"
UTC, NY = ZoneInfo("UTC"), ZoneInfo("America/New_York")
PIP = {"EURGBPm": 1e-4, "AUDNZDm": 1e-4, "AUDUSDm": 1e-4, "USDCNHm": 1e-4, "GBPUSDm": 1e-4, "EURUSDm": 1e-4,
       "USDJPYm": 0.01, "XAUUSDm": 0.1, "US30m": 1.0, "USTECm": 1.0, "US500m": 0.1}
FILES = {"EURUSDm": ["EURUSDm_2016", "EURUSDm", "EURUSDm_2026_10"], "GBPUSDm": ["GBPUSDm_2016", "GBPUSDm", "GBPUSDm_2026"],
         "USDJPYm": ["USDJPYm_2016", "USDJPYm", "USDJPYm_2026_10"], "XAUUSDm": ["XAUUSDm_2015", "XAUUSDm"]}
B = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
W10 = (pd.Timestamp("2016-10-01"), pd.Timestamp("2026-10-01"))
W2 = (pd.Timestamp("2024-10-01"), pd.Timestamp("2026-10-01"))
RNG = np.random.default_rng(20261020)
OUT = []


def load(sym, extra=()):
    cols = B + list(extra)
    if sym in FILES:
        parts = [pd.read_parquet(DATA / f"{f}_m1.parquet", columns=cols) for f in FILES[sym] if (DATA / f"{f}_m1.parquet").exists()]
    else:
        f = EXPLORE / f"{sym}_m1.parquet"
        parts = [pd.read_parquet(f if f.exists() else DATA / f"{sym}_m1.parquet", columns=cols)]
    df = pd.concat(parts).sort_index()
    df = df[~df.index.duplicated()]
    return df[(df.index >= "2016-01-01") & (df.index < "2026-10-01")]


class M:
    """Minute arrays plus a trade simulator: entry at the open of minute i (ask for a buy, bid for a sell), exit at
    the open of minute j; stop/target are price distances from the entry; the stop wins ties; a gap through the stop
    fills at the open."""
    def __init__(self, df, pip):
        self.idx_ = df.index
        self.t = df.index.values.astype("datetime64[m]").astype(np.int64)
        self.pip = pip
        for c in B:
            setattr(self, c, df[c].to_numpy())

    def i(self, ts, tol=5):
        k = np.datetime64(pd.Timestamp(ts).tz_localize(None) if pd.Timestamp(ts).tzinfo is None
                          else pd.Timestamp(ts).tz_convert(UTC).tz_localize(None), "m").astype(np.int64)
        n = int(np.searchsorted(self.t, k))
        return n if n < len(self.t) and self.t[n] - k <= tol else None

    def sim(self, i, j, side, stop_d, tp_d=None):
        if i is None or j is None or j <= i:
            return None
        if side > 0:
            e = self.aopen[i]
            lo, hi = self.blow[i:j], self.bhigh[i:j]
            s = np.nonzero(lo <= e - stop_d)[0]
            g = np.nonzero(hi >= e + tp_d)[0] if tp_d else []
        else:
            e = self.bopen[i]
            lo, hi = self.alow[i:j], self.ahigh[i:j]
            s = np.nonzero(hi >= e + stop_d)[0]
            g = np.nonzero(lo <= e - tp_d)[0] if tp_d else []
        s = s[0] if len(s) else 10**9
        g = g[0] if len(g) else 10**9
        if s <= g and s < 10**9:
            k = i + s
            if side > 0:
                x = min(e - stop_d, self.bopen[k]) if s > 0 else e - stop_d
            else:
                x = max(e + stop_d, self.aopen[k]) if s > 0 else e + stop_d
            return side * (x - e), k
        if g < 10**9:
            return tp_d, i + g
        x = self.bopen[j] if side > 0 else self.aopen[j]
        return side * (x - e), j


def run(m, sigs):
    """sigs: time-ordered (entry_minute_index, exit_minute_index, side, stop_d, tp_d, cost_price). No overlap.
    Returns live and random-direction trades: rows of (entry time, pips, R)."""
    live, ctrl, busy = [], [], -1
    for i, j, side, stop_d, tp_d, cost in sigs:
        if i is None or j is None or i <= busy or stop_d <= 0:
            continue
        r = m.sim(i, j, side, stop_d, tp_d)
        if r is None:
            continue
        pnl, k = r
        busy = k
        pnl -= cost
        ts = m.idx_[i]
        live.append((ts, pnl / m.pip, pnl / stop_d))
        rs = int(RNG.choice([-1, 1]))
        rr = m.sim(i, j, rs, stop_d, tp_d)
        if rr:
            ctrl.append((ts, rr[0] / m.pip, rr[0] / stop_d))
    return pd.DataFrame(live, columns=["ts", "pips", "R"]), pd.DataFrame(ctrl, columns=["ts", "pips", "R"])


def tstat(x):
    x = np.asarray(x, float)
    return x.mean() / x.std(ddof=1) * np.sqrt(len(x)) if len(x) > 2 and x.std() > 0 else np.nan


def equity(R, risk=0.02):
    eq = peak = 1000.0
    dd = 0.0
    for r in R:
        eq *= 1 + risk * max(r, -3)
        peak = max(peak, eq)
        dd = max(dd, 1 - eq / peak)
    return eq, dd


def stats(df, w):
    d = df[(df.ts >= w[0]) & (df.ts < w[1])]
    if d.empty:
        return dict(n=0)
    eq, dd = equity(d.R)
    return dict(n=len(d), pips=round(d.pips.mean(), 2), R=round(d.R.mean(), 3), t=round(tstat(d.R), 2),
                win=round((d.R > 0).mean() * 100, 1), eur=round(eq), dd=round(dd * 100, 1))


def report(name, live, ctrl):
    if live.empty:
        print(f"\n{name}: no trades")
        OUT.append(dict(name=name, n=0, passes=False))
        return
    h1 = live[live.ts < "2022-01-01"].R
    h2 = live[live.ts >= "2022-01-01"].R
    a, b = stats(live, W10), stats(live, W2)
    ok = len(h1) > 10 and len(h2) > 10 and h1.mean() > 0 and h2.mean() > 0 and a["t"] > 2.8 \
        and live.R.mean() > (ctrl.R.mean() if len(ctrl) else -9)
    OUT.append(dict(name=name, passes=bool(ok), ten_years=a, two_years=b, dev_R=round(h1.mean(), 3) if len(h1) else None,
                    hold_R=round(h2.mean(), 3), random_R=round(ctrl.R.mean(), 3) if len(ctrl) else None))
    print(f"\n{'PASS' if ok else 'fail'}  {name}")
    for lab, s in (("10 yrs", a), ("2 yrs ", b)):
        if s["n"]:
            print(f"   {lab}: {s['n']:5} trades {s['pips']:+7.2f} pips {s['R']:+.3f}R (t {s['t']:5.2f}) win {s['win']:4.1f}%"
                  f"  EUR 1,000 -> {s['eur']:>6,} (max drop {s['dd']:.0f}%)")
    print(f"   2016-21 {h1.mean() if len(h1) else float('nan'):+.3f}R | 2022-26 {h2.mean():+.3f}R | "
          f"random direction {ctrl.R.mean() if len(ctrl) else float('nan'):+.3f}R")


def mid_bars(df, rule):
    mid = (df.bclose + df.aclose) / 2
    o = ((df.bopen + df.aopen) / 2).resample(rule, label="right", closed="left").first()
    h = ((df.bhigh + df.ahigh) / 2).resample(rule, label="right", closed="left").max()
    lo = ((df.blow + df.alow) / 2).resample(rule, label="right", closed="left").min()
    c = mid.resample(rule, label="right", closed="left").last()
    return pd.DataFrame(dict(o=o, h=h, l=lo, c=c)).dropna()


# ---------------------------------------------------------------- ideas
def zrev(sym, ez, sz, ok_hour, name):
    df = load(sym)
    m = M(df, PIP[sym])
    h = mid_bars(df, "1h")
    del df
    mu, sd = h.c.rolling(20).mean().to_numpy(), h.c.rolling(20).std().to_numpy()
    c = h.c.to_numpy()
    z = (c - mu) / sd
    ts = h.index
    sigs = []
    for k in range(21, len(h)):
        if not ok_hour(ts[k].hour):
            continue
        side = -1 if (z[k] > ez and z[k - 1] <= ez) else +1 if (z[k] < -ez and z[k - 1] >= -ez) else 0
        if not side:
            continue
        stop_px = mu[k] - side * sz * sd[k]
        # exit at the first later H1 close back through 0, at most 48 h
        ex = ts[k] + pd.Timedelta(hours=48)
        for q in range(k + 1, min(k + 60, len(h))):
            if ts[q] > ex:
                break
            if (side > 0 and z[q] >= 0) or (side < 0 and z[q] <= 0):
                ex = ts[q]
                break
        i = m.i(ts[k])
        if i is None:
            continue
        e = m.aopen[i] if side > 0 else m.bopen[i]
        stop_d = side * (e - stop_px)
        sigs.append((i, m.i(ex, tol=180), side, stop_d, None, 0.0))
    report(name, *run(m, sigs))


def Q1():
    zrev("EURGBPm", 2.0, 3.5, lambda hr: 7 <= hr <= 16, "Q1 EURGBP H1 z-score +-2 fade (Qwen)")


def G4():
    zrev("AUDNZDm", 2.5, 4.0, lambda hr: hr < 20, "G4 AUDNZD H1 z-score +-2.5 fade (Gemini)")


def Q2():
    a, c = load("AUDUSDm"), load("USDCNHm")
    m = M(a, PIP["AUDUSDm"])
    ha, hc = mid_bars(a, "1h"), mid_bars(c, "1h")
    del a, c
    j = ha[["c"]].join(hc[["c"]], lsuffix="_a", rsuffix="_c", how="inner")
    lowc = j.c_c <= j.c_c.rolling(20).min()
    highc = j.c_c >= j.c_c.rolling(20).max()
    a_hi = j.c_a >= j.c_a.rolling(20).max()
    a_lo = j.c_a <= j.c_a.rolling(20).min()
    sigs = []
    for t, lc, hc_, ah, al, px in zip(j.index, lowc, highc, a_hi, a_lo, j.c_a):
        if not 1 <= t.hour <= 8:
            continue
        side = +1 if (lc and not ah) else -1 if (hc_ and not al) else 0
        if side:
            t0 = t + pd.Timedelta(minutes=15)
            sigs.append((m.i(t0), m.i(t0 + pd.Timedelta(hours=3)), side, 0.0015 * px, 0.0025 * px, 0.0))
    report("Q2 USDCNH new 20h extreme -> AUDUSD catch-up (Qwen)", *run(m, sigs))


def Q3():
    df = load("GBPUSDm")
    m = M(df, PIP["GBPUSDm"])
    del df
    sigs = []
    for d in pd.bdate_range("2016-01-04", "2026-09-30"):
        i0, i9, i12 = m.i(d + pd.Timedelta(hours=7)), m.i(d + pd.Timedelta(hours=9)), m.i(d + pd.Timedelta(hours=12))
        if None in (i0, i9, i12):
            continue
        p0, p9 = (m.aopen[i0] + m.bopen[i0]) / 2, (m.aopen[i9] + m.bopen[i9]) / 2
        r = p9 / p0 - 1
        if abs(r) > 0.0025:
            sigs.append((i9, i12, -int(np.sign(r)), 0.0015 * p9, None, 0.0))
    report("Q3 GBPUSD fade a >0.25% 07-09 UTC move to 12:00 (Qwen)", *run(m, sigs))


def Q4():
    g, u = load("XAUUSDm"), load("USDJPYm")
    m = M(g, PIP["XAUUSDm"])
    hg, hu = mid_bars(g, "1h"), mid_bars(u, "1h")
    del g, u
    j = hg.join(hu[["h"]], rsuffix="_u", how="inner")
    brk = j.h_u > j.h_u.shift(1).rolling(20).max()
    sigs = []
    for t, b, o, c in zip(j.index, brk, j.o, j.c):
        if 13 <= t.hour <= 16 and b and c >= o:
            sigs.append((m.i(t), m.i(t + pd.Timedelta(hours=2)), +1, 0.0020 * c, 0.0025 * c, 0.0))
    report("Q4 USDJPY breaks out but gold holds -> buy gold (Qwen)", *run(m, sigs))


def ny_close(df):
    mid = (df.bclose + df.aclose) / 2
    loc = mid.tz_localize("UTC").tz_convert(NY)
    s = loc[(loc.index.hour == 15) & (loc.index.minute == 59)]
    s.index = s.index.date
    return s[~s.index.duplicated()]


def Q5():
    d30, dtc = load("US30m"), load("USTECm")
    m30, mtc = M(d30, 1.0), M(dtc, 1.0)
    r = (ny_close(d30) / ny_close(dtc)).dropna()
    del d30, dtc
    z = ((r - r.rolling(20).mean()) / r.rolling(20).std()).shift(1)   # known before today's open
    lives, ctrls = [], []
    for sym, mm, cond in (("USTEC", mtc, z > 2), ("US30", m30, z < -2)):
        sigs = []
        for d in z.index[cond.fillna(False).to_numpy()]:
            t0 = datetime.combine(d, time(9, 30), NY)
            i = mm.i(t0)
            if i is None:
                continue
            px = mm.aopen[i]
            sigs.append((i, mm.i(datetime.combine(d, time(15, 0), NY)), +1, 0.0025 * px, 0.004 * px, 0.0))
        lv, ct = run(mm, sigs)
        lives.append(lv)
        ctrls.append(ct)
    report("Q5 US30/USTEC ratio z>2: buy the laggard at the open (Qwen)",
           pd.concat(lives).sort_values("ts"), pd.concat(ctrls).sort_values("ts"))


def yahoo():
    y = pd.read_parquet(DATA / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    return y.pivot(index="date", columns="sym", values="close").sort_index().ffill()


def G3():
    df = load("US500m")
    m = M(df, PIP["US500m"])
    b = mid_bars(df, "15min")
    del df
    Y = yahoo()
    spx = Y["^GSPC"].dropna()
    above = (spx > spx.rolling(200).mean()).shift(1)          # yesterday's close vs its 200-day average
    above.index = pd.to_datetime(above.index).date
    irx = Y["^IRX"].dropna()
    irx.index = pd.to_datetime(irx.index)
    d = b.c.diff()
    up, dn = d.clip(lower=0).ewm(alpha=0.5, adjust=False).mean(), (-d.clip(upper=0)).ewm(alpha=0.5, adjust=False).mean()
    rsi = (100 - 100 / (1 + up / dn)).to_numpy()
    tr = pd.concat([b.h - b.l, (b.h - b.c.shift()).abs(), (b.l - b.c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14).mean().to_numpy()
    ts = b.index
    loc = ts.tz_localize("UTC").tz_convert(NY)
    sigs = []
    k = 15
    while k < len(b):
        hm = loc[k].hour * 60 + loc[k].minute
        if rsi[k] < 10 and 9 * 60 + 45 <= hm <= 16 * 60 and loc[k].weekday() < 5 and above.get(loc[k].date(), False):
            q = k + 1
            while q < len(b) and rsi[q] <= 70:
                q += 1
            if q >= len(b):
                break
            i, j = m.i(ts[k]), m.i(ts[q], tol=30)
            if i is not None and j is not None:
                nights = (loc[q].normalize() - loc[k].normalize()).days + (1 if loc[q].hour >= 17 > loc[k].hour else 0)
                rate = irx.asof(pd.Timestamp(loc[k].date())) + 2.5
                px = m.aopen[i]
                sigs.append((i, j, +1, 3 * atr[k], None, px * rate / 100 / 360 * max(nights, 0)))
            k = q
        k += 1
    report("G3 US500 RSI(2)<10 on M15 in an uptrend, exit RSI>70 (Gemini)", *run(m, sigs))


def boj(d):
    return -0.1 if d < date(2024, 3, 19) else 0.1 if d < date(2024, 7, 31) else 0.25 if d < date(2025, 1, 24) else 0.5


def G2():
    df = load("USDJPYm")
    m = M(df, PIP["USDJPYm"])
    loc = df.index
    hi = ((df.bhigh + df.ahigh) / 2).resample("1D").max()      # calendar-day range for the ATR
    lo = ((df.blow + df.alow) / 2).resample("1D").min()
    del df
    vix = pd.read_csv(EXPLORE / "vix.csv", index_col=0, parse_dates=True).iloc[:, 0]
    vix.index = vix.index.date
    Y = yahoo()
    irx = Y["^IRX"].dropna()
    irx.index = pd.to_datetime(irx.index)
    days, closes = [], []
    for d in pd.bdate_range("2016-01-04", "2026-09-29"):
        i = m.i(d + pd.Timedelta(hours=22, minutes=15), tol=10)
        if i is not None:
            days.append((d.date(), i))
            closes.append((m.aopen[i] + m.bopen[i]) / 2)
    c = pd.Series(closes, index=[d for d, _ in days])
    ema = c.ewm(span=100, adjust=False).mean()
    rng = pd.Series((hi - lo).to_numpy(), index=hi.index.date).reindex(c.index)
    atr = pd.concat([rng, (c - c.shift()).abs()], axis=1).max(axis=1).rolling(14).mean()

    def go(use_vix):
        live = []
        k = 100
        while k < len(days):
            d, i = days[k]
            v = vix.get(d)
            if c.iloc[k] > ema.iloc[k] and (not use_vix or (v is not None and v < 20)):
                e = m.aopen[i]
                init = 2.5 * atr.iloc[k]
                best = c.iloc[k]
                q = k + 1
                exit_px, exit_k = None, None
                while q < len(days):
                    dq, iq = days[q]
                    stop = best - 2.5 * atr.iloc[q - 1]
                    seg = np.nonzero(m.blow[days[q - 1][1]:iq] <= stop)[0]
                    if seg.size:
                        exit_px, exit_k = stop, q
                        break
                    vq = vix.get(dq)
                    if c.iloc[q] < ema.iloc[q] or (use_vix and vq is not None and vq > 22):
                        exit_px, exit_k = m.bopen[iq], q
                        break
                    best = max(best, c.iloc[q])
                    q += 1
                if exit_px is None:
                    break
                nights = (days[exit_k][0] - d).days
                rate = irx.asof(pd.Timestamp(d)) - boj(d) - 1.0
                carry_px = e * rate / 100 / 360 * nights
                pnl = exit_px - e + carry_px
                live.append((pd.Timestamp(d), pnl / m.pip, pnl / init, nights))
                k = exit_k
            k += 1
        return pd.DataFrame(live, columns=["ts", "pips", "R", "nights"])
    lv, ct = go(True), go(False)
    print(f"   (average hold {lv.nights.mean():.0f} days with VIX, {ct.nights.mean():.0f} without)")
    report("G2 USDJPY carry while VIX<20 and above EMA100 (Gemini); control = no VIX filter", lv, ct)


def G5():
    for sym in ("GBPUSDm", "XAUUSDm"):
        df = load(sym, extra=["n"])
        m = M(df, PIP[sym])
        b = mid_bars(df, "5min")
        b["n"] = df.n.resample("5min", label="right", closed="left").sum().reindex(b.index)
        del df
        gc.collect()
        mb = b.c.rolling(20).mean()
        sd = b.c.rolling(20).std()
        upb, lob = (mb + 2.5 * sd).to_numpy(), (mb - 2.5 * sd).to_numpy()
        vol = (b.n > 3 * b.n.shift(1).rolling(50).mean()).to_numpy()
        c, rngb, mbv = b.c.to_numpy(), (b.h - b.l).to_numpy(), mb.to_numpy()
        ts = b.index
        sigs = []
        for k in range(60, len(b) - 1):
            hm = ts[k].hour * 60 + ts[k].minute
            if 20 * 60 + 55 <= hm < 23 * 60 or not vol[k]:
                continue
            side = -1 if c[k] > upb[k] else +1 if c[k] < lob[k] else 0
            if not side:
                continue
            q = k + 1
            while q < min(k + 25, len(b)) and not ((side < 0 and c[q] <= mbv[q]) or (side > 0 and c[q] >= mbv[q])):
                q += 1
            sigs.append((m.i(ts[k], tol=2), m.i(ts[min(q, len(b) - 1)], tol=30), side, 1.5 * rngb[k], None, 0.0))
        report(f"G5 {sym[:6]} M5 Bollinger 2.5 + 3x tick volume fade (Gemini)", *run(m, sigs))
        del m, b
        gc.collect()


def nfp_days(m, pip):
    def rng(d):
        i, j = m.i(datetime.combine(d, time(8, 30), NY)), m.i(datetime.combine(d, time(8, 45), NY))
        if i is None or j is None:
            return None
        return (m.ahigh[i:j].max() - m.blow[i:j].min()) / pip
    out = []
    for y in range(2016, 2027):
        for mo in range(1, 13):
            twelfth = date(y, mo, 12)
            sat = twelfth + timedelta(days=(5 - twelfth.weekday()) % 7)
            cand = sat + timedelta(days=20)
            if cand > date(2026, 9, 30) or cand < date(2016, 2, 1):
                continue
            for d in (cand, cand + timedelta(days=7)):
                r = rng(d)
                normal = [x for x in (rng(d - timedelta(days=k)) for k in (1, 2, 3, 4)) if x]
                if r and normal and r > 2 * np.median(normal):
                    out.append(d)
                    break
    return out


def G1():
    for sym in ("EURUSDm", "USDJPYm"):
        df = load(sym)
        m = M(df, PIP[sym])
        del df
        days = nfp_days(m, PIP[sym])
        sigs = []
        for d in days:
            i0, i1 = m.i(datetime.combine(d, time(8, 30), NY)), m.i(datetime.combine(d, time(8, 45), NY))
            j = m.i(datetime.combine(d, time(20, 55), UTC))
            if None in (i0, i1, j):
                continue
            mv = (m.aopen[i1] + m.bopen[i1]) / 2 - (m.aopen[i0] + m.bopen[i0]) / 2
            if mv == 0:
                continue
            side = int(np.sign(mv))
            hi, lo = m.ahigh[i0:i1].max(), m.blow[i0:i1].min()
            e = m.aopen[i1] if side > 0 else m.bopen[i1]
            stop_d = (e - lo) if side > 0 else (hi - e)
            sigs.append((i1, j, side, stop_d, None, 0.0))
        print(f"   {sym}: {len(days)} NFP days found")
        report(f"G1 {sym[:6]} follow the NFP first-15-min move to 21:00 UTC (Gemini)", *run(m, sigs))
        del m
        gc.collect()


if __name__ == "__main__":
    for k in sys.argv[1:] or ["Q1", "G4", "Q2", "Q3", "Q4", "Q5", "G3", "G2", "G5", "G1"]:
        try:
            globals()[k]()
        except FileNotFoundError as e:
            print(f"\n{k}: data missing ({e})")
        gc.collect()
    f = HERE / "lab4_results.json"
    old = {r["name"]: r for r in json.loads(f.read_text())} if f.exists() else {}
    old.update({r["name"]: r for r in OUT})
    f.write_text(json.dumps(list(old.values()), indent=1, default=str))
