"""Gotobi lab: do add-ons (EMA filters, news days, moving stops, take-profits, extra trades, ATR sizing,
regime and day-type filters, other entry/exit times) improve the plain Gotobi bot? 2016-2026 Exness bid/ask minutes.

Testing rules, fixed before any result was looked at:
  * Universe: the 752 trades the production bot made in its own 2016-2026 replay
    (results/bot_trades_2016_2026.csv). The lab must reproduce every one of them first.
  * Fills: the bot's simulator rules (market orders at the minute's open bid/ask + 0.2 bp slippage; server
    stops scanned minute by minute, gaps fill at the open; stop assumed first if stop and target share a minute).
  * Every input is known at decision time: completed candles only, scheduled event dates.
  * Score: Sharpe of the per-slot result in R (1R = the risk used for sizing). A skipped trade counts as 0,
    so trading less is not free, and the score does not depend on the risk % chosen later.
  * Selection on 2016-2021 ('design') only; 2022-2026 ('hold-out') is judged once.
    Walk-forward: from 2019, each year uses the family member that scored best on all earlier years.
    Filters are compared with random filters that skip the same number of trades.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

import gotobi as G

ROOT = Path(__file__).resolve().parent.parent
DATA, RES = ROOT / "data", ROOT / "results"
SLIP, PIP, CONTRACT = 0.2e-4, 0.01, 100_000
SPLIT = pd.Timestamp("2022-01-01")
WF_YEARS = list(range(2019, 2027))
RNG = np.random.default_rng(7)


def minutes(ts) -> np.ndarray | int:
    if isinstance(ts, (pd.Series, pd.DatetimeIndex, np.ndarray)):
        return pd.DatetimeIndex(ts).values.astype("datetime64[m]").astype(np.int64)
    return int(np.datetime64(pd.Timestamp(ts).to_datetime64(), "m").astype(np.int64))


# ---------------------------------------------------------------------------------------------- market
class Market:
    COLS = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]

    def __init__(self):
        files = ["USDJPYm_2016_m1.parquet", "USDJPYm_m1.parquet", "USDJPYm_2026_10_m1.parquet"]
        df = pd.concat([pd.read_parquet(DATA / f, columns=self.COLS) for f in files]).sort_index()
        self.df = df[~df.index.duplicated()]
        self.t = minutes(self.df.index)
        self.bo, self.bh, self.bl, self.bc, self.ao, self.ah, self.al, self.ac = (
            self.df[c].to_numpy() for c in self.COLS)

    def quote(self, m: int) -> tuple[float, float]:
        """(bid, ask) a market order at minute m gets: the minute's open, or the last close if no tick yet."""
        i = int(np.searchsorted(self.t, m, side="right")) - 1
        if self.t[i] == m:
            return self.bo[i], self.ao[i]
        return self.bc[i], self.ac[i]

    def at(self, m: int) -> int:
        return int(np.searchsorted(self.t, m, side="left"))


@dataclass
class Leg:
    side: int
    m_in: int
    m_out: int
    raw: float          # ask (long) / bid (short) the order saw; stops are set from it, as the bot does
    entry: float
    exit: float
    sl: float | None
    risk: float         # pips used for sizing: the stop distance, or a notional one when there is no stop
    size: float
    pnl: float          # pips, after spread and slippage
    why: str

    @property
    def r(self) -> float:
        return self.size * self.pnl / self.risk


def run_leg(M: Market, m0: int, m1: int, side: int, stop: float | None = 55.0, tp: float | None = None,
            risk: float | None = None, size: float = 1.0, be: float | None = None, be_lock: float = 1.0,
            trail: float | None = None) -> Leg:
    """Market order at minute m0, closed at minute m1 unless the stop / target fills first."""
    bid0, ask0 = M.quote(m0)
    raw = ask0 if side > 0 else bid0
    entry = raw * (1 + side * SLIP)
    sl = round(raw - side * stop * PIP, 3) if stop else None
    tpx = round(raw + side * tp * PIP, 3) if tp else None
    i0, i1 = M.at(m0), M.at(m1)
    lo, hi, op = (M.bl, M.bh, M.bo) if side > 0 else (M.ah, M.al, M.ao)   # adverse, favourable, open
    k, px, why = None, None, "time"
    if be is None and trail is None:
        ks = kt = None
        if sl is not None:
            h = np.flatnonzero(lo[i0:i1] <= sl) if side > 0 else np.flatnonzero(lo[i0:i1] >= sl)
            ks = i0 + int(h[0]) if len(h) else None
        if tpx is not None:
            h = np.flatnonzero(hi[i0:i1] >= tpx) if side > 0 else np.flatnonzero(hi[i0:i1] <= tpx)
            kt = i0 + int(h[0]) if len(h) else None
        if ks is not None and (kt is None or ks <= kt):
            k, why = ks, "stop"
            px = min(sl, op[k]) if side > 0 else max(sl, op[k])
        elif kt is not None:
            k, why = kt, "target"
            px = max(tpx, op[k]) if side > 0 else min(tpx, op[k])
    else:
        cur, peak = sl, raw
        for j in range(i0, i1):
            if cur is not None and ((side > 0 and lo[j] <= cur) or (side < 0 and lo[j] >= cur)):
                k, why = j, ("stop" if cur == sl else "trail")
                px = min(cur, op[j]) if side > 0 else max(cur, op[j])
                break
            if tpx is not None and ((side > 0 and hi[j] >= tpx) or (side < 0 and hi[j] <= tpx)):
                k, why = j, "target"
                px = max(tpx, op[j]) if side > 0 else min(tpx, op[j])
                break
            peak = max(peak, hi[j]) if side > 0 else min(peak, hi[j])
            gain = (peak - raw) * side / PIP
            new = cur
            if be is not None and gain >= be:
                lock = round(raw + side * be_lock * PIP, 3)
                new = lock if new is None else (max(new, lock) if side > 0 else min(new, lock))
            if trail is not None and gain >= trail:
                tr = round(peak - side * trail * PIP, 3)
                new = tr if new is None else (max(new, tr) if side > 0 else min(new, tr))
            cur = new
    if k is None:
        bid1, ask1 = M.quote(m1)
        px, m_out = (bid1 if side > 0 else ask1), m1
    else:
        m_out = int(M.t[k])
    ex = px * (1 - side * SLIP)
    pnl = (ex - entry) * side / PIP
    rk = (raw - sl) * side / PIP if sl is not None else risk
    return Leg(side, m0, m_out, raw, entry, ex, sl, rk, size, pnl, why)


# ---------------------------------------------------------------------------------------------- slots + features
def load_slots() -> pd.DataFrame:
    bt = pd.read_csv(RES / "bot_trades_2016_2026.csv")
    g = pd.to_datetime(bt.gotobi)
    opened = pd.to_datetime(bt.opened, utc=True).dt.tz_localize(None)
    S = pd.DataFrame({"gotobi": g, "opened": opened, "bot_entry": bt.entry_price, "bot_close": bt.close_price,
                      "bot_reason": bt.reason})
    S["m_in"] = minutes(S.opened)
    S["m_exit"] = minutes(S.gotobi + pd.Timedelta(minutes=54))
    S["m_fix"] = minutes(S.gotobi + pd.Timedelta(minutes=55))
    S["year"] = S.gotobi.dt.year
    return S


def daily_bars(M: Market) -> pd.DataFrame:
    """New-York-close daily candles (mid) from the Exness minutes; Yahoo daily before 2016 only to warm up
    the long averages (Yahoo's FX 'close' is unreliable, so the next day's open stands in for it)."""
    d = M.df
    mid_h, mid_l = (d.bhigh + d.ahigh) / 2, (d.blow + d.alow) / 2
    mid_o, mid_c = (d.bopen + d.aopen) / 2, (d.bclose + d.aclose) / 2
    key = (d.index.tz_localize("UTC").tz_convert("America/New_York") + pd.Timedelta(hours=7)).normalize()
    key = key.tz_localize(None)
    day = pd.DataFrame({"open": mid_o.groupby(key).first(), "high": mid_h.groupby(key).max(),
                        "low": mid_l.groupby(key).min(), "close": mid_c.groupby(key).last(),
                        "n": mid_c.groupby(key).size(),
                        "close_t": pd.Series(d.index, index=d.index).groupby(key).last() + pd.Timedelta(minutes=1)})
    day = day[day.n >= 120].drop(columns="n")
    y = pd.read_parquet(DATA / "daily_yahoo.parquet")
    y = y[y.sym == "USDJPY=X"].assign(date=lambda x: pd.to_datetime(x.date)).set_index("date").sort_index()
    y = y[y.high > y.low]
    y = y.assign(close=y.open.shift(-1), close_t=y.index + pd.Timedelta(hours=22))
    y = y[y.index < day.index[0]].dropna()[["open", "high", "low", "close", "close_t"]]
    day = pd.concat([y, day])
    prev = day.close.shift()
    tr = pd.concat([day.high - day.low, (day.high - prev).abs(), (day.low - prev).abs()], axis=1).max(axis=1)
    day["atr"] = tr.rolling(14).mean() / PIP
    day["atr_med"] = day.atr.rolling(260).median()
    day["atr_rank"] = day.atr.rolling(260).apply(lambda a: (a <= a[-1]).mean(), raw=True)
    for n in (20, 50, 100, 200):
        day[f"ema{n}"] = day.close.ewm(span=n, adjust=False).mean()
    for n in (1, 5, 20):
        day[f"ret{n}"] = day.close / day.close.shift(n) - 1
    day["hi60"] = day.high.rolling(60).max()
    return day


def features(M: Market, S: pd.DataFrame) -> pd.DataFrame:
    F = pd.DataFrame(index=S.index)
    E = S.opened
    # --- daily (last New York close completed before the entry)
    day = daily_bars(M)
    i = np.searchsorted(day.close_t.values, E.values, side="right") - 1
    D = day.iloc[i].reset_index(drop=True)
    F["d_close"] = D.close.values
    for n in (20, 50, 100, 200):
        F[f"D1_ema{n}"] = D[f"ema{n}"].values
    for c in ("atr", "atr_med", "atr_rank", "ret1", "ret5", "ret20"):
        F[c] = D[c].values
    F["dd60"] = (D.close / D.hi60 - 1).values
    F["d_ema_up"] = (D.ema50 > D.ema200).values & (D.ema20 > D.ema50).values
    # --- intraday candles (UTC-aligned), last completed before the entry
    mid = (M.df.bclose + M.df.aclose) / 2
    for tf, freq in (("H1", "1h"), ("H4", "4h")):
        c = mid.resample(freq).last().dropna()
        end = (c.index + pd.Timedelta(freq)).values
        j = np.searchsorted(end, E.values, side="right") - 1
        F[f"{tf}_close"] = c.to_numpy()[j]
        for n in (20, 50, 100, 200):
            F[f"{tf}_ema{n}"] = c.ewm(span=n, adjust=False).mean().to_numpy()[j]
    F["D1_close"] = F.d_close
    # --- the entry day so far (New York day start -> entry)
    ny = E.dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    start = ((ny + pd.Timedelta(hours=7)).dt.normalize() - pd.Timedelta(hours=7)).dt.tz_convert("UTC").dt.tz_localize(None)
    hi_m, lo_m = ((M.df.bhigh + M.df.ahigh) / 2).to_numpy(), ((M.df.blow + M.df.alow) / 2).to_numpy()
    pre_rng, pre_move, ldn = [], [], []
    for s0, e0 in zip(minutes(start), minutes(E)):
        a, b = M.at(s0), M.at(e0)
        if b - a < 5:
            pre_rng.append(np.nan)
            pre_move.append(np.nan)
        else:
            pre_rng.append((hi_m[a:b].max() - lo_m[a:b].min()) / PIP)
            pre_move.append((mid.iat[b - 1] - (M.bo[a] + M.ao[a]) / 2) / PIP)
        l0 = M.at(e0 - (e0 % 1440) + 7 * 60)            # 07:00 UTC on the entry's UTC date
        ldn.append((mid.iat[b - 1] - (M.bo[l0] + M.ao[l0]) / 2) / PIP if l0 < b - 5 else np.nan)
    F["pre_range"], F["pre_move"], F["london_move"] = pre_rng, pre_move, ldn
    F["pre_ratio"] = F.pre_range / F.atr
    bid, ask = zip(*(M.quote(m) for m in S.m_in))
    F["spread_in"] = (np.array(ask) - np.array(bid)) / PIP
    # --- carry: US 3-month bill minus the BoJ rate, as of the previous day
    diff = G.rate_series(pd.Timestamp("2015-06-01"), pd.Timestamp("2026-12-31"))
    dprev = S.opened.dt.normalize() - pd.Timedelta(days=1)
    F["carry"] = diff.reindex(dprev).values
    F["carry_trend"] = F.carry - diff.reindex(dprev - pd.Timedelta(days=91)).values
    # --- scheduled events
    ev = pd.read_csv(DATA / "events_calendar.csv", parse_dates=["date", "time_utc"])
    exit_t = S.gotobi + pd.Timedelta(minutes=54)
    for e in ("fomc", "fomc_minutes"):
        ts = ev[ev.event == e].time_utc.dropna().values
        F[f"{e}_in"] = [bool(((ts >= a) & (ts < b)).any()) for a, b in zip(E.values, exit_t.values)]
    boj = set(ev[ev.event == "boj"].date.dt.normalize())
    F["boj_day"] = S.gotobi.isin(boj).values
    F["boj_eve"] = [any(x in boj for x in pd.date_range(a.normalize(), g - pd.Timedelta(days=1)))
                    for a, g in zip(E, S.gotobi)]
    # --- day type
    jp = holidays.Japan(years=range(2015, 2028))
    def bday(x):
        return x.weekday() < 5 and x not in jp and (x.month, x.day) not in ((12, 31), (1, 2), (1, 3))
    nominal, month_end = [], []
    for g in S.gotobi:
        nominal.append(min(int(np.ceil(g.day / 5) * 5), 30))
        nxt = g + pd.Timedelta(days=1)
        while not bday(nxt.date()):
            nxt += pd.Timedelta(days=1)
        month_end.append(nxt.month != g.month)
    F["nominal"], F["month_end"] = nominal, month_end
    F["moved"] = S.gotobi.dt.day.values != F.nominal.values
    F["monday"] = (S.opened.dt.weekday == 6).values | (S.opened.dt.weekday == 5).values
    F["wd"] = S.gotobi.dt.weekday.values
    return F


# ---------------------------------------------------------------------------------------------- variants
def build_variants(M: Market, S: pd.DataFrame, F: pd.DataFrame, base: list[Leg]) -> list[dict]:
    V = []
    n = len(S)
    keep_all = np.ones(n, bool)

    def filt(fam, name, mask, note=""):
        mask = np.asarray(mask, bool)
        V.append(dict(fam=fam, name=name, legs=[[base[k]] if mask[k] else [] for k in range(n)], mask=mask, note=note))

    def legs(fam, name, fn, note=""):
        V.append(dict(fam=fam, name=name, legs=[fn(k) for k in range(n)], mask=None, note=note))

    def sized(fam, name, w, note=""):
        w = np.asarray(w, float)
        V.append(dict(fam=fam, name=name, mask=None, note=note,
                      legs=[[Leg(**{**base[k].__dict__, "size": w[k]})] if w[k] > 0 else [] for k in range(n)]))

    V.append(dict(fam="base", name="BASE: the bot as it is", legs=[[b] for b in base], mask=keep_all, note=""))

    # T: trend / EMA filters (long only if the last completed candle closed above / below its EMA)
    for tf in ("H1", "H4", "D1"):
        for p in (20, 50, 100, 200):
            above = F[f"{tf}_close"].values > F[f"{tf}_ema{p}"].values
            filt("T ema", f"only above {tf} EMA{p}", above)
            filt("T ema", f"only below {tf} EMA{p}", ~above)
    filt("T ema", "only D1 EMAs stacked up (20>50>200)", F.d_ema_up)
    filt("T ema", "skip D1 EMAs stacked up", ~F.d_ema_up.values)
    up = F.D1_close.values > F.D1_ema200.values
    sized("T ema", "size 1.5x above D1 EMA200, 0.5x below", np.where(up, 1.5, 0.5))
    up = F.H4_close.values > F.H4_ema50.values
    sized("T ema", "size 1.5x above H4 EMA50, 0.5x below", np.where(up, 1.5, 0.5))

    # N: news days
    fomc, mins, boj, eve = (F[c].values for c in ("fomc_in", "fomc_minutes_in", "boj_day", "boj_eve"))
    filt("N news", "skip FOMC decision in the trade", ~fomc)
    filt("N news", "skip FOMC decision or minutes in the trade", ~(fomc | mins))
    filt("N news", "skip BoJ decision day (fix day)", ~boj)
    filt("N news", "skip BoJ decision on fix day or day before", ~(boj | eve))
    filt("N news", "skip all Fed + BoJ event days", ~(fomc | mins | boj | eve))
    pr = F.pre_ratio.fillna(0).values
    filt("N news", "skip wild entry day (range so far > 1.0 ATR)", pr <= 1.0)
    filt("N news", "skip wild entry day (range so far > 0.8 ATR)", pr <= 0.8)
    filt("N news", "skip quiet entry day (range so far < 0.4 ATR)", pr >= 0.4)

    # S: stop-loss variants (sized by the stop distance; 'no stop' sized as if the stop were 55)
    for s in (30, 40, 75, 100, 150):
        legs("S stop", f"fixed stop {s} pips", lambda k, s=s: [run_leg(M, S.m_in[k], S.m_exit[k], 1, stop=s)])
    legs("S stop", "no stop at all (sized as 55)", lambda k: [run_leg(M, S.m_in[k], S.m_exit[k], 1, stop=None, risk=55.6)])
    atr = F.atr.values
    for a in (0.5, 0.75, 1.0, 1.5, 2.0):
        legs("S stop", f"ATR stop {a} x ATR14(D1)",
             lambda k, a=a: [run_leg(M, S.m_in[k], S.m_exit[k], 1, stop=round(a * atr[k], 1))])
    for b in (15, 25, 40):
        legs("S stop", f"breakeven after +{b} pips", lambda k, b=b: [run_leg(M, S.m_in[k], S.m_exit[k], 1, be=b)])
    for tr in (20, 30, 50):
        legs("S stop", f"trailing stop {tr} pips", lambda k, tr=tr: [run_leg(M, S.m_in[k], S.m_exit[k], 1, trail=tr)])

    # P: take-profit variants
    for tp in (20, 30, 50, 80):
        legs("P target", f"take profit +{tp} pips", lambda k, tp=tp: [run_leg(M, S.m_in[k], S.m_exit[k], 1, tp=tp)])
    for a in (0.25, 0.5, 0.75):
        legs("P target", f"take profit {a} x ATR",
             lambda k, a=a: [run_leg(M, S.m_in[k], S.m_exit[k], 1, tp=round(a * atr[k], 1))])
    for tp in (20, 30):
        legs("P target", f"half off at +{tp}, rest to the fix",
             lambda k, tp=tp: [run_leg(M, S.m_in[k], S.m_exit[k], 1, tp=tp, size=0.5),
                               run_leg(M, S.m_in[k], S.m_exit[k], 1, size=0.5)])

    # Z: position sizing
    med = F.atr_med.values
    sized("Z sizing", "ATR sizing: risk x median/ATR (0.5-2x)", np.clip(med / atr, 0.5, 2.0))
    sized("Z sizing", "ATR sizing: risk x median/ATR (0.67-1.5x)", np.clip(med / atr, 0.67, 1.5))
    rb = np.array([b.r for b in base])
    last10 = np.array([rb[max(0, k - 10):k].sum() if k >= 10 else 1.0 for k in range(n)])
    sized("Z sizing", "half size after a losing last-10", np.where(last10 < 0, 0.5, 1.0))
    sized("Z sizing", "skip after a losing last-10", np.where(last10 < 0, 0.0, 1.0))

    # X: extra trades
    m_tokyo = (S.gotobi.map(minutes) - 60).values           # 23:00 UTC = 08:00 JST, Tokyo desks open
    for mins_ in (30, 60, 120):
        legs("X extra", f"+ short after the fix, {mins_} min",
             lambda k, mm=mins_: [base[k], run_leg(M, S.m_fix[k], S.m_fix[k] + mm, -1)])
    legs("X extra", "+ half-size short after the fix, 60 min",
         lambda k: [base[k], run_leg(M, S.m_fix[k], S.m_fix[k] + 60, -1, size=0.5)])
    for surge in (0, 10, 20):
        def fn(k, surge=surge):
            b = base[k]
            if b.why == "time" and b.pnl >= surge:
                return [b, run_leg(M, S.m_fix[k], S.m_fix[k] + 60, -1)]
            return [b]
        legs("X extra", f"+ short after the fix only if the long made >= {surge} pips", fn)

    def open_pnl(k, m):
        b = base[k]
        if b.why != "time" and b.m_out <= m:
            return None
        bid, _ = M.quote(m)
        return (bid - b.entry) / PIP
    for g in (10, 20):
        def fn(k, g=g):
            p = open_pnl(k, m_tokyo[k])
            add = p is not None and p >= g
            return [base[k]] + ([run_leg(M, m_tokyo[k], S.m_exit[k], 1, stop=30)] if add else [])
        legs("X extra", f"+ add a long at 23:00 UTC if up >= {g} pips", fn)
    for g in (15, 30):
        def fn(k, g=g):
            p = open_pnl(k, m_tokyo[k])
            add = p is not None and p <= -g
            return [base[k]] + ([run_leg(M, m_tokyo[k], S.m_exit[k], 1, stop=30)] if add else [])
        legs("X extra", f"+ add a long at 23:00 UTC if down >= {g} pips", fn)
    def reentry(k):
        b = base[k]
        if b.why == "stop" and b.m_out < m_tokyo[k]:
            return [b, run_leg(M, m_tokyo[k], S.m_exit[k], 1, stop=30)]
        return [b]
    legs("X extra", "+ re-buy at 23:00 UTC after a stop-out", reentry)
    legs("X extra", "+ always add a long at 23:00 UTC",
         lambda k: [base[k], run_leg(M, m_tokyo[k], S.m_exit[k], 1, stop=30)])

    # D: day types
    nom, me, mon, moved = F.nominal.values, F.month_end.values, F.monday.values, F.moved.values
    filt("D day", "only the 25th / 30th", nom >= 25)
    filt("D day", "only the 5th-20th", nom < 25)
    filt("D day", "only 5th, 10th, 25th, 30th", np.isin(nom, (5, 10, 25, 30)))
    filt("D day", "only month-end", me)
    filt("D day", "skip Monday fixes (Sunday-reopen entry)", ~mon)
    filt("D day", "skip moved days (weekend/holiday)", ~moved)
    sized("D day", "size 1.5x on 25th/30th, 0.75x else", np.where(nom >= 25, 1.5, 0.75))

    # R: market regime
    ar = F.atr_rank.values
    filt("R regime", "skip top-10% volatility (ATR rank)", ar <= 0.9)
    filt("R regime", "skip top-20% volatility (ATR rank)", ar <= 0.8)
    filt("R regime", "skip bottom-20% volatility", ar >= 0.2)
    r5, r20, dd60 = F.ret5.values, F.ret20.values, F.dd60.values
    filt("R regime", "skip after a 5-day fall > 1.5%", r5 > -0.015)
    filt("R regime", "skip after a 5-day fall > 3%", r5 > -0.03)
    filt("R regime", "only if up over 20 days", r20 > 0)
    filt("R regime", "skip if > 5% below the 60-day high", dd60 > -0.05)
    filt("R regime", "only if the rate gap widened (3 months)", F.carry_trend.fillna(0).values > 0)
    lm = F.london_move.fillna(0).values
    filt("R regime", "skip after a London surge > +40 pips", lm < 40)
    filt("R regime", "skip after a London drop > 40 pips", lm > -40)

    # E: entry time (exit 00:54 UTC, 55-pip stop; Sunday entries 15 min after the reopen, as the bot does)
    def entry_at(k, hhmm):
        h, mm = map(int, hhmm.split(":"))
        day0 = S.gotobi[k] - pd.Timedelta(days=1) if h >= 12 else S.gotobi[k]
        m = minutes(day0 + pd.Timedelta(hours=h, minutes=mm))
        i = M.at(m)
        if M.t[i] - m > 30:
            m = int(M.t[i]) + 15
        return m
    for hhmm in ("12:55", "13:55", "14:55", "17:55", "19:55", "21:55", "23:00"):
        legs("E entry", f"enter {hhmm} UTC", lambda k, h=hhmm: [run_leg(M, entry_at(k, h), S.m_exit[k], 1)])

    # Q: exit time
    for off in (-24, -9, -4, 1, 6):
        legs("Q exit", f"exit at 00:{54 + off:02d} UTC" if 54 + off < 60 else f"exit at 01:{54 + off - 60:02d} UTC",
             lambda k, o=off: [run_leg(M, S.m_in[k], S.m_exit[k] + o, 1)])
    return V


# ---------------------------------------------------------------------------------------------- scoring
def slot_r(v) -> np.ndarray:
    return np.array([sum(l.r for l in ls) for ls in v["legs"]])


def sharpe(r: np.ndarray, per_year: float) -> float:
    sd = r.std(ddof=1)
    return float(r.mean() / sd * np.sqrt(per_year)) if sd > 0 else 0.0


def max_dd_r(r: np.ndarray) -> float:
    eq = np.concatenate([[0.0], np.cumsum(r)])
    return float((np.maximum.accumulate(eq) - eq).max())


def random_filter_p(rb: np.ndarray, mask: np.ndarray, per_year: float, obs: float, draws: int = 4000) -> float:
    n, q = len(rb), int(mask.sum())
    if q in (0, n):
        return np.nan
    idx = np.argsort(RNG.random((draws, n)), axis=1)[:, :q]
    r = np.zeros((draws, n))
    np.put_along_axis(r, idx, rb[idx], axis=1)
    sd = r.std(axis=1, ddof=1)
    sh = r.mean(axis=1) / sd * np.sqrt(per_year)
    return float(np.mean(sh >= obs))


def walk_forward(R: dict[str, np.ndarray], years: np.ndarray, per_year: float) -> tuple[np.ndarray, list[str]]:
    out, picks = [], []
    for y in WF_YEARS:
        tr, te = years < y, years == y
        best = max(R, key=lambda k: sharpe(R[k][tr], per_year))
        picks.append(best)
        out.append(R[best][te])
    return np.concatenate(out), picks


def main():
    M = Market()
    S = load_slots()
    base = [run_leg(M, S.m_in[k], S.m_exit[k], 1) for k in range(len(S))]
    # 1) the lab must reproduce the bot's own replay, trade by trade
    e_err = max(abs(b.entry - x) for b, x in zip(base, S.bot_entry))
    c_err = max(abs(b.exit - x) for b, x in zip(base, S.bot_close))
    why_ok = sum((b.why == "stop") == (x == "stop") for b, x in zip(base, S.bot_reason))
    print(f"reproduce the bot: {why_ok}/{len(S)} exits of the same kind, max entry error {e_err:.2e}, "
          f"max exit error {c_err:.2e}")
    assert why_ok == len(S) and e_err < 1e-6 and c_err < 1e-6, "lab does not match the bot"
    F = features(M, S)
    V = build_variants(M, S, F, base)
    years = S.year.values
    per_year = len(S) / ((S.gotobi.iloc[-1] - S.gotobi.iloc[0]).days / 365.25)
    des, hol = (S.gotobi < SPLIT).values, (S.gotobi >= SPLIT).values
    rb = slot_r(V[0])
    rows = []
    for v in V:
        r = slot_r(v)
        v["r"] = r
        traded = np.array([len(ls) > 0 for ls in v["legs"]])
        allr = np.array([l.r for ls in v["legs"] for l in ls])
        row = dict(fam=v["fam"], name=v["name"], trades=int(traded.sum()), legs=len(allr),
                   win=float(np.mean(allr > 0)) if len(allr) else np.nan,
                   avg_r=float(r[traded].mean()) if traded.any() else np.nan,
                   sh_des=sharpe(r[des], per_year), sh_hol=sharpe(r[hol], per_year), sh_all=sharpe(r, per_year),
                   R_des=float(r[des].sum()), R_hol=float(r[hol].sum()), dd_r=max_dd_r(r),
                   worst=float(min(allr)) if len(allr) else np.nan,
                   sh_16_18=sharpe(r[years <= 2018], per_year), sh_19_21=sharpe(r[(years >= 2019) & des], per_year))
        if v["mask"] is not None and v["fam"] != "base":
            row["p_random"] = random_filter_p(rb[des], v["mask"][des], per_year, row["sh_des"])
        rows.append(row)
    T = pd.DataFrame(rows)
    b = T.iloc[0]
    T["d_des"], T["d_hol"] = T.sh_des - b.sh_des, T.sh_hol - b.sh_hol
    pd.to_pickle(dict(S=S, F=F, V=[{k: v[k] for k in ("fam", "name", "r")} for v in V], T=T), RES / "lab_results.pkl")
    T.to_csv(RES / "lab_variants.csv", index=False)
    lines = []

    def p(s=""):
        print(s)
        lines.append(s)

    p(f"Gotobi lab, {len(S)} slots {S.gotobi.iloc[0].date()} -> {S.gotobi.iloc[-1].date()} ({per_year:.1f}/yr), "
      f"{len(V) - 1} variants. Design 2016-2021 ({des.sum()} slots), hold-out 2022-2026 ({hol.sum()} slots).")
    p("Score = yearly Sharpe of the per-slot result in R (skipped trade = 0). 'p rand' = share of random filters "
      "(same number of trades skipped) that scored at least as well in design.")
    p(f"BASE: design Sharpe {b.sh_des:.2f}, hold-out {b.sh_hol:.2f}, all {b.sh_all:.2f}; avg {b.avg_r:+.3f}R/trade, "
      f"win {b.win:.0%}, worst {b.worst:+.2f}R, max DD {b.dd_r:.1f}R")
    for fam, g in T[T.fam != "base"].groupby("fam", sort=False):
        p(f"\n=== {fam}")
        p(f"  {'variant':48s} {'trades':>6} {'avg R':>7} {'win':>4} | {'design':>6} {'Δ':>6} {'16-18':>6} {'19-21':>6}"
          f" | {'hold-out':>8} {'Δ':>6} | {'worst':>6} {'p rand':>6}")
        for _, r in g.sort_values("sh_des", ascending=False).iterrows():
            pr = f"{r.p_random:6.3f}" if "p_random" in r and pd.notna(r.get("p_random")) else "     -"
            p(f"  {r['name'][:48]:48s} {r.trades:6d} {r.avg_r:+7.3f} {r.win:4.0%} | {r.sh_des:6.2f} {r.d_des:+6.2f} "
              f"{r.sh_16_18:6.2f} {r.sh_19_21:6.2f} | {r.sh_hol:8.2f} {r.d_hol:+6.2f} | {r.worst:+6.2f} {pr}")
        # design winner -> hold-out, and walk-forward over the family (base always allowed)
        members = {v["name"]: v["r"] for v in V if v["fam"] in (fam, "base")}
        best = max((k for k in members if not k.startswith("BASE")), key=lambda k: sharpe(members[k][des], per_year))
        wf, picks = walk_forward(members, years, per_year)
        base_wf = rb[years >= WF_YEARS[0]]
        p(f"  design pick: '{best}' -> hold-out Sharpe {sharpe(members[best][hol], per_year):.2f} "
          f"vs base {b.sh_hol:.2f}")
        p(f"  walk-forward 2019-2026: Sharpe {sharpe(wf, per_year):.2f} vs base {sharpe(base_wf, per_year):.2f}; "
          f"picks by year: " + ", ".join(f"{y % 100:02d}:{'BASE' if k.startswith('BASE') else k[:28]}"
                                         for y, k in zip(WF_YEARS, picks)))
    (RES / "lab_report.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
