"""Fabio Valentini's NASDAQ scalping model (Chart Fanatics, https://youtu.be/tvERE-Beu2U), tested mechanically.
Codex builds its own version independently in codex_audit/fabio_model (same transcript, no access to this code).

What the video says (transcript minutes 2-48): two models on auction market theory and the volume profile, stops of
5-10 NQ ticks, 0.2-0.5% risk, ~2,400 trades a year, whole position off at the target.
 TREND (New York session only): the market must be OUT OF BALANCE - outside the previous day's value area; the
   location is the low-volume node (LVN) of the impulse leg; the trigger is aggression (big trades) at the LVN; the
   stop sits just beyond it; the target is the point of control (POC) of the previous balance area; break-even early.
 MEAN REVERSION (London session; also "perfect for the summer"): the market is in balance (previous day's profile);
   skip the first breakout out of value; once price is back inside, take the SECOND swing at its LVN, target the
   POC, stop just beyond, break-even after an additional breakout.

Mechanical version (fixed before running; "my choice" where the video gives no number):
 - Profiles are TIME AT PRICE (Market Profile TPO): every minute spreads one unit over its high-low range in bins of
   2 bp of price. We have no exchange volume (the CFD tick count is not volume, and 2016-19 HistData has none), so
   one method is used for all 10 years. Value area = 70% around the POC; balance = the previous RTH session
   (09:30-16:00 New York).
 - TREND: entries 09:35-15:30 NY, flat 15:58. Out of balance = a minute closing above yesterday's VAH (long) or
   below its VAL (short). Leg = from the session extreme on the other side to the running extreme; LVN = the
   thinnest bin in the middle 20-80% of the leg's own profile.
 - MEAN REVERSION: London 03:00-09:25 NY, flat 09:29. A first close outside yesterday's value area, then a close back
   inside; leg = from the breakout extreme to the running extreme back inside; LVN of that leg; target = yesterday's
   POC (needs >= 1R). Variant MRs: the same rules in the New York session, May-August only.
 - Trigger (the order-flow step cannot be seen in CFD data), two versions:
     L  limit order resting at the LVN once it is formed (filled when the ask/bid trades through it);
     C  confirmation: a minute touches the LVN, the next minute closes back in the trade direction, enter at the
        following minute's open (a price-action stand-in for "aggression").
 - Stop: beyond the LVN (L) or beyond the touch bar (C) by 3 x the 1-minute ATR(30) (my choice; his 5-10 ticks
   are smaller than one CFD spread before 2024); never closer than 3 spreads.
 - Target: TREND - the nearest earlier balance POC (sessions 2-20 back) beyond the entry and >= 1.5R away, else
   2.5R (my choice); MEAN REVERSION - yesterday's POC.
 - Break-even: the stop moves to the entry once price is +1R. At most 3 trades a day per model; one at a time.
Costs: real Exness bid/ask (USTEC/US500 from Aug 2019); before that HistData bid + the Exness spread for that New
York minute of Aug 2019 - Jul 2020. Scenario FUT: the same trades at a futures-like 0.3 bp round-trip cost.
Pass: positive in both halves (to 2021 / from 2022), beats the same entries in a random direction, t > 2.8.
Reported for the last 10 years, the last 2 years and 2026, EUR 1,000 at 0.5% (Fabio's risk) and 2%.

  python strategies/fabio/lab9.py [USTECm US500m]
"""
import gc
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NY = ZoneInfo("America/New_York")
B8 = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
HD = {"USTECm": "NSXUSD", "US500m": "SPXUSD"}
RNG = np.random.default_rng(20261021)
WINDOWS = {"10 yrs (2016-10..2026-09)": ("2016-10-01", "2026-10-01"), "2 yrs (2024-10..2026-09)": ("2024-10-01", "2026-10-01"),
           "2026 (Jan..Sep)": ("2026-01-01", "2026-10-01")}
OUT = []


def load(sym):
    ex = pd.read_parquet(ROOT / "data" / f"{sym}_m1.parquet", columns=B8)
    ex = ex[ex.index < "2026-10-01"]
    hd = pd.read_parquet(HERE / "data" / f"{HD[sym]}_hd_bid_m1.parquet")
    hd = hd[hd.index < "2019-08-05"]
    ref = ex[(ex.index >= "2019-08-05") & (ex.index < "2020-08-01")]
    loc = ref.index.tz_localize("UTC").tz_convert(NY)
    prof = (ref.aopen - ref.bopen).groupby(loc.hour * 60 + loc.minute).median()
    hl = hd.index.tz_localize("UTC").tz_convert(NY)
    sp = prof.reindex(hl.hour * 60 + hl.minute).fillna(prof.median()).to_numpy()
    old = pd.DataFrame({"bopen": hd.bopen, "bhigh": hd.bhigh, "blow": hd.blow, "bclose": hd.bclose,
                        "aopen": hd.bopen + sp, "ahigh": hd.bhigh + sp, "alow": hd.blow + sp, "aclose": hd.bclose + sp}, index=hd.index)
    df = pd.concat([old, ex[ex.index >= "2019-08-05"]]).sort_index()
    return df[~df.index.duplicated()]


def profile(hi, lo, step):
    """Time-at-price histogram: each minute spreads one unit evenly over its range."""
    base = np.floor(lo.min() / step)
    nb = int(np.floor(hi.max() / step) - base) + 1
    a = (np.floor(lo / step) - base).astype(int)
    b = (np.floor(hi / step) - base).astype(int)
    w = 1.0 / (b - a + 1)
    d = np.zeros(nb + 1)
    np.add.at(d, a, w)
    np.add.at(d, b + 1, -w)
    return np.cumsum(d)[:nb], base


def value_area(hi, lo, step):
    h, base = profile(hi, lo, step)
    poc = int(h.argmax())
    lo_i = hi_i = poc
    tot, acc = h.sum(), h[poc]
    while acc < 0.7 * tot and (lo_i > 0 or hi_i < len(h) - 1):
        up = h[hi_i + 1] if hi_i < len(h) - 1 else -1
        dn = h[lo_i - 1] if lo_i > 0 else -1
        if up >= dn:
            hi_i += 1
            acc += up
        else:
            lo_i -= 1
            acc += dn
    return (base + poc + 0.5) * step, (base + hi_i + 1) * step, (base + lo_i) * step      # POC, VAH, VAL


def lvn(hi, lo, a, b, step):
    """Thinnest time-at-price bin in the middle 20-80% of the leg a..b (prices)."""
    lo_p, hi_p = min(a, b), max(a, b)
    keep = (hi >= lo_p) & (lo <= hi_p)                      # minutes that traded inside the leg
    if keep.sum() < 3 or hi_p - lo_p < 3 * step:
        return None
    h, base = profile(np.minimum(hi[keep], hi_p), np.maximum(lo[keep], lo_p), step)
    prices = (base + np.arange(len(h)) + 0.5) * step
    inner = (prices > lo_p + 0.2 * (hi_p - lo_p)) & (prices < lo_p + 0.8 * (hi_p - lo_p))
    if inner.sum() < 2:
        return None
    k = np.argmin(np.where(inner, h, np.inf))
    return prices[k]


def simulate(day, side, entry_i, entry_px, stop_px, tgt_px, flat_i, be=True):
    """Bid/ask fill engine on one day's minute arrays. Returns R (after costs) or None."""
    risk = abs(entry_px - stop_px)
    if risk <= 0:
        return None
    stop = stop_px
    for k in range(entry_i, flat_i):
        # stop first (conservative); a gap through the stop fills at the open
        if side > 0 and day["blow"][k] <= stop:
            return ((min(stop, day["bopen"][k]) if k > entry_i else stop) - entry_px) / risk, k
        if side < 0 and day["ahigh"][k] >= stop:
            return (entry_px - (max(stop, day["aopen"][k]) if k > entry_i else stop)) / risk, k
        if k > entry_i:
            if side > 0 and day["bhigh"][k] >= tgt_px:
                return (tgt_px - entry_px) / risk, k
            if side < 0 and day["alow"][k] <= tgt_px:
                return (entry_px - tgt_px) / risk, k
            if be:
                fav = (day["bhigh"][k] - entry_px) if side > 0 else (entry_px - day["alow"][k])
                if fav >= risk:
                    stop = entry_px
    x = day["bopen"][flat_i] if side > 0 else day["aopen"][flat_i]
    return side * (x - entry_px) / risk, flat_i


def run_day(day, model, trig, vah, val, poc, prior_pocs, atr, cost_bp, be=True, stop_k=3.0, trend_rr=1.5, mr_rr=1.0,
            entry_end=None):
    """One session of one model. day: dict of arrays for that session window; returns list of (R, random-R, side).
    Options for the improvement search: be (break-even at +1R), stop_k (stop = stop_k x ATR), trend_rr (minimum R:R of
    a POC target), mr_rr (minimum R:R to yesterday's POC), entry_end (no new entries after this minute index)."""
    mid_h = (day["ahigh"] + day["bhigh"]) / 2
    mid_l = (day["alow"] + day["blow"]) / 2
    mid_c = (day["aclose"] + day["bclose"]) / 2
    n = len(mid_c)
    step = mid_c[0] * 2e-4
    trades, k, last_exit = [], 1, 0
    state = 0          # mean reversion: 0 waiting for the first breakout, 1 outside, 2 back inside
    a_ext = None
    last_entry = n - 3 if entry_end is None else min(n - 3, entry_end)
    while k < last_entry and len(trades) < 3:
        if k < last_exit:
            k += 1
            continue
        side, leg_a = 0, None
        if model == "trend":
            if mid_c[k] > vah:
                side, leg_a, leg_b = 1, mid_l[:k + 1].min(), mid_h[:k + 1].max()
            elif mid_c[k] < val:
                side, leg_a, leg_b = -1, mid_h[:k + 1].max(), mid_l[:k + 1].min()
        else:
            if state == 0 and (mid_c[k] < val or mid_c[k] > vah):
                state, a_ext, out_side = 1, mid_c[k], (1 if mid_c[k] < val else -1)
            elif state == 1:
                a_ext = min(a_ext, mid_l[k]) if out_side > 0 else max(a_ext, mid_h[k])
                if val <= mid_c[k] <= vah:
                    state, back_k = 2, k
            if state == 2:
                side = out_side
                leg_a = a_ext
                leg_b = mid_h[back_k:k + 1].max() if side > 0 else mid_l[back_k:k + 1].min()
        if not side:
            k += 1
            continue
        lv = lvn(mid_h[:k + 1], mid_l[:k + 1], leg_a, leg_b, step)
        if lv is None:
            k += 1
            continue
        # wait for the pullback to the LVN from the next minute on
        touched = None
        for q in range(k + 1, n - 2):
            if (side > 0 and mid_l[q] <= lv < mid_h[q - 1] + 1e-12) or (side < 0 and mid_h[q] >= lv > mid_l[q - 1] - 1e-12):
                touched = q
                break
            if (side > 0 and mid_h[q] > leg_b) or (side < 0 and mid_l[q] < leg_b):      # leg extends: re-evaluate later
                break
        if touched is None:
            k = q if q > k else k + 1
            continue
        if trig == "L":
            ei = touched
            e_px = lv + (day["aclose"][touched] - day["bclose"][touched]) / 2 * (1 if side > 0 else -1)
            stop_px = lv - side * max(stop_k * atr, 3 * (day["aclose"][touched] - day["bclose"][touched]))
        else:
            if touched + 2 >= n:
                break
            c_ok = (mid_c[touched + 1] > lv) if side > 0 else (mid_c[touched + 1] < lv)
            if not c_ok:
                k = touched + 1
                continue
            ei = touched + 2
            e_px = day["aopen"][ei] if side > 0 else day["bopen"][ei]
            ext = mid_l[touched:ei].min() if side > 0 else mid_h[touched:ei].max()
            stop_px = ext - side * max(stop_k * atr, 3 * (day["aopen"][ei] - day["bopen"][ei]))
        risk = abs(e_px - stop_px)
        if model == "trend":
            cands = [p for p in prior_pocs if side * (p - e_px) >= trend_rr * risk]
            tgt = (min(cands, key=lambda p: abs(p - e_px)) if cands else e_px + side * max(2.5, trend_rr) * risk)
        else:
            tgt = poc
            if side * (tgt - e_px) < mr_rr * risk:
                k = touched + 1
                continue
        flat_i = n - 1
        res = simulate(day, side, ei, e_px, stop_px, tgt, flat_i, be=be)
        if res is None:
            k = touched + 1
            continue
        r, exit_k = res
        r -= cost_bp * 1e-4 * e_px / risk                       # extra cost scenario (0 for real spreads)
        rs = int(RNG.choice([-1, 1]))
        e_r = e_px if rs == side else (day["bopen"][ei] if rs < 0 else day["aopen"][ei])
        rr = simulate(day, rs, ei, e_r, e_r - rs * risk, e_r + rs * abs(tgt - e_px), flat_i, be=be)
        trades.append((r, rr[0] if rr else None, side))
        last_exit = exit_k + 1                                  # one position at a time
        k = last_exit
        state = 0 if model == "mr" else state
    return trades


def sessions(df):
    """Yield (date, NY-session arrays, London-session arrays, RTH high/low arrays) per weekday."""
    loc = df.index.tz_localize("UTC").tz_convert(NY)
    mod = loc.hour * 60 + loc.minute
    dates = loc.date
    arr = {c: df[c].to_numpy() for c in B8}
    order = np.argsort(dates, kind="stable")
    uniq, start = np.unique(dates[order], return_index=True)
    bounds = list(start) + [len(order)]
    for u, s, e in zip(uniq, bounds[:-1], bounds[1:]):
        if pd.Timestamp(u).weekday() >= 5:
            continue
        idx = order[s:e]
        m = mod[idx]
        ny = idx[(m >= 570) & (m <= 958)]
        ld = idx[(m >= 180) & (m <= 569)]
        yield u, {c: arr[c][ny] for c in B8}, {c: arr[c][ld] for c in B8}


def stats(r, start, end, dates):
    sel = (dates >= np.datetime64(start)) & (dates < np.datetime64(end))
    x = r[sel]
    if len(x) < 3:
        return dict(n=int(len(x)))
    out = dict(n=int(len(x)), R=round(float(x.mean()), 3), t=round(float(x.mean() / x.std(ddof=1) * np.sqrt(len(x))), 2),
               win=round(float((x > 0).mean() * 100), 1))
    for risk in (0.005, 0.02):
        eq = 1000 * np.cumprod(1 + risk * np.maximum(x, -3))
        peak = np.maximum.accumulate(np.r_[1000, eq])
        out[f"eur_{risk:.1%}"] = round(float(eq[-1]))
        out[f"dd_{risk:.1%}"] = round(float((1 - np.r_[1000, eq] / peak).max() * 100), 1)
    return out


def main():
    syms = sys.argv[1:] or ["USTECm", "US500m"]
    for sym in syms:
        df = load(sym)
        print(f"\n######## {sym}: {df.index[0]:%Y-%m-%d} .. {df.index[-1]:%Y-%m-%d}")
        days = list(sessions(df))
        del df
        gc.collect()
        prof = []
        for u, ny, ld in days:
            if len(ny["bclose"]) < 300:
                prof.append(None)
                continue
            mh, ml = (ny["ahigh"] + ny["bhigh"]) / 2, (ny["alow"] + ny["blow"]) / 2
            prof.append(value_area(mh, ml, mh.mean() * 2e-4))
        results = {}
        for model, trig, cost, label in (("trend", "L", 0.0, "TREND, limit at LVN"), ("trend", "C", 0.0, "TREND, confirmation"),
                                         ("mr", "L", 0.0, "MEAN REVERSION London, limit"), ("mr", "C", 0.0, "MEAN REVERSION London, confirmation"),
                                         ("mrs", "C", 0.0, "MEAN REVERSION NY, May-Aug, confirmation"),
                                         ("trend", "C", None, "TREND, confirmation, FUTURES-like cost"),
                                         ("mr", "C", None, "MEAN REVERSION London, confirmation, FUTURES-like cost")):
            rows = []
            for i in range(21, len(days)):
                u, ny, ld = days[i]
                if prof[i - 1] is None or len(ny["bclose"]) < 300:
                    continue
                poc, vah, val = prof[i - 1]
                prior_pocs = [p[0] for p in prof[max(0, i - 20):i - 1] if p is not None]
                sess = ny if model in ("trend", "mrs") else ld
                if model == "mrs" and pd.Timestamp(u).month not in (5, 6, 7, 8):
                    continue
                if len(sess["bclose"]) < 120:
                    continue
                if cost is None:                         # futures-like: replace the spread by 0.3 bp round trip
                    mid = {c: (sess["a" + c] + sess["b" + c]) / 2 for c in ("open", "high", "low", "close")}
                    sess = {**{"b" + c: mid[c] * (1 - 0.15e-4) for c in mid}, **{"a" + c: mid[c] * (1 + 0.15e-4) for c in mid}}
                mh, ml = (sess["ahigh"] + sess["bhigh"]) / 2, (sess["alow"] + sess["blow"]) / 2
                atr = float(mh[0] * 1e-4)                    # fallback: 1 bp of price
                prev = days[i - 1][1]
                atr = float(np.mean(((prev["ahigh"] + prev["bhigh"]) - (prev["alow"] + prev["blow"]))[-30:] / 2)) if len(prev["bclose"]) > 30 else atr
                for r, rr, side in run_day(sess, "mr" if model == "mrs" else model, trig, vah, val, poc, prior_pocs, atr, 0.0):
                    rows.append((np.datetime64(u), r, rr))
            if not rows:
                print(f"  {label}: no trades")
                continue
            d = np.array([x[0] for x in rows])
            r = np.array([x[1] for x in rows], float)
            rr = np.array([x[2] for x in rows if x[2] is not None], float)
            h1, h2 = r[d < np.datetime64("2022-01-01")], r[d >= np.datetime64("2022-01-01")]
            tt = r.mean() / r.std(ddof=1) * np.sqrt(len(r))
            ok = len(h1) > 10 and len(h2) > 10 and h1.mean() > 0 and h2.mean() > 0 and r.mean() > rr.mean() and tt > 2.8
            rec = dict(name=f"{sym[:-1]} {label}", passes=bool(ok), half_2016_21=round(float(h1.mean()), 3) if len(h1) else None,
                       half_2022_26=round(float(h2.mean()), 3) if len(h2) else None, random=round(float(rr.mean()), 3))
            print(f"\n{'PASS' if ok else 'fail'}  {sym[:-1]} {label}   (2016-21 {rec['half_2016_21']}R | 2022-26 {rec['half_2022_26']}R | random {rec['random']}R)")
            for wn, (a, b) in WINDOWS.items():
                s = stats(r, a, b, d)
                rec[wn] = s
                if s["n"] >= 3:
                    print(f"   {wn:26}: {s['n']:5} trades {s['R']:+.3f}R (t {s['t']:5.2f}) win {s['win']:4.1f}% | EUR 1,000 at 0.5%: "
                          f"{s['eur_0.5%']:>6,} (drop {s['dd_0.5%']:.0f}%) | at 2%: {s['eur_2.0%']:>7,} (drop {s['dd_2.0%']:.0f}%)")
            OUT.append(rec)
        del days, prof
        gc.collect()
    f = HERE / "lab9_results.json"
    old = json.loads(f.read_text()) if f.exists() else {}
    old.update({r["name"]: r for r in OUT})
    f.write_text(json.dumps(old, indent=1, default=str))


if __name__ == "__main__":
    main()
