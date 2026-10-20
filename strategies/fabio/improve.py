"""Can Fabio's model be made profitable on CFDs? A small, fixed menu of changes, chosen on 2016-2021 ONLY, then judged
once on 2022-2026 and reported for the last 10 years, the last 2 years and 2026 (EUR 1,000 at 0.5% and 2%).

Menu (written before running), real Exness costs, confirmation trigger (the better one in lab9):
 TREND (NY): break-even on/off x stop 2 or 4 ATR x minimum target 1.5R or 2.5R x entries all session or only the
   first 2 hours x all months or no June-August (he says summer compression hurts the trend model) = 32 versions.
 MEAN REVERSION (London): break-even on/off x stop 2 or 4 ATR x minimum target 1.0R or 1.5R x all months or
   May-August only (he says it is "perfect for the summer") = 16 versions.
Choice: highest average R in 2016-2021 among versions with >= 100 design trades. The chosen version is then run
unchanged on 2022-2026 and on the S&P 500 as a cross-check.

  python strategies/fabio/improve.py
"""
import gc
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab9  # noqa: E402


def prepare(sym):
    df = lab9.load(sym)
    days = list(lab9.sessions(df))
    del df
    gc.collect()
    prof = []
    for u, ny, ld in days:
        if len(ny["bclose"]) < 300:
            prof.append(None)
            continue
        mh, ml = (ny["ahigh"] + ny["bhigh"]) / 2, (ny["alow"] + ny["blow"]) / 2
        prof.append(lab9.value_area(mh, ml, mh.mean() * 2e-4))
    return days, prof


def trades(days, prof, model, opts, months=None):
    rows = []
    for i in range(21, len(days)):
        u, ny, ld = days[i]
        if prof[i - 1] is None or len(ny["bclose"]) < 300:
            continue
        if months is not None and pd.Timestamp(u).month not in months:
            continue
        poc, vah, val = prof[i - 1]
        sess = ny if model == "trend" else ld
        if len(sess["bclose"]) < 120:
            continue
        prev = days[i - 1][1]
        atr = float(np.mean(((prev["ahigh"] + prev["bhigh"]) - (prev["alow"] + prev["blow"]))[-30:] / 2)) \
            if len(prev["bclose"]) > 30 else float(sess["bclose"][0] * 1e-4)
        prior = [p[0] for p in prof[max(0, i - 20):i - 1] if p is not None]
        for r, rr, side in lab9.run_day(sess, model, "C", vah, val, poc, prior, atr, 0.0, **opts):
            rows.append((np.datetime64(u), r, rr))
    d = np.array([x[0] for x in rows])
    return d, np.array([x[1] for x in rows], float), np.array([x[2] if x[2] is not None else np.nan for x in rows], float)


def menu():
    out = []
    for be, sk, rr, first2h, nosummer in itertools.product((True, False), (2.0, 4.0), (1.5, 2.5), (False, True), (False, True)):
        out.append(("trend", dict(be=be, stop_k=sk, trend_rr=rr, entry_end=120 if first2h else None),
                    (1, 2, 3, 4, 5, 9, 10, 11, 12) if nosummer else None,
                    f"TREND be={be} stop={sk:.0f}ATR minRR={rr} {'first2h' if first2h else 'allday'} {'noSummer' if nosummer else 'allMonths'}"))
    for be, sk, rr, summer in itertools.product((True, False), (2.0, 4.0), (1.0, 1.5), (False, True)):
        out.append(("mr", dict(be=be, stop_k=sk, mr_rr=rr), (5, 6, 7, 8) if summer else None,
                    f"MR-London be={be} stop={sk:.0f}ATR minRR={rr} {'May-Aug' if summer else 'allMonths'}"))
    return out


def main():
    days, prof = prepare("USTECm")
    rows = []
    cut = np.datetime64("2022-01-01")
    results = {}
    for model, opts, months, name in menu():
        d, r, rr = trades(days, prof, model, opts, months)
        des, hold = r[d < cut], r[d >= cut]
        rows.append(dict(model=model, name=name, design_n=len(des), design_R=float(des.mean()) if len(des) else np.nan,
                         hold_n=len(hold), hold_R=float(hold.mean()) if len(hold) else np.nan))
        results[name] = (d, r, rr)
        print(f"  {name:62} design {len(des):4} trades {des.mean() if len(des) else float('nan'):+.3f}R | (hold-out hidden)", flush=True)
    grid = pd.DataFrame(rows)
    grid.to_csv(HERE / "improve_grid.csv", index=False)
    chosen = {}
    for model in ("trend", "mr"):
        g = grid[(grid.model == model) & (grid.design_n >= 100)].sort_values("design_R", ascending=False)
        chosen[model] = g.iloc[0]["name"]
        print(f"\nCHOSEN on 2016-2021 for {model}: {chosen[model]}  (design {g.iloc[0]['design_R']:+.3f}R, {g.iloc[0]['design_n']} trades)")
    print("\n=== The chosen versions, judged once ===")
    rep = {}
    for model, name in chosen.items():
        d, r, rr = results[name]
        rec = {"design_R": round(float(r[d < cut].mean()), 3), "holdout_R": round(float(r[d >= cut].mean()), 3),
               "holdout_t": round(float(r[d >= cut].mean() / r[d >= cut].std(ddof=1) * np.sqrt((d >= cut).sum())), 2),
               "random_R": round(float(np.nanmean(rr)), 3)}
        print(f"\nNASDAQ {name}: 2016-21 {rec['design_R']:+.3f}R | 2022-26 {rec['holdout_R']:+.3f}R (t {rec['holdout_t']}) | random {rec['random_R']:+.3f}R")
        for wn, (a, b) in lab9.WINDOWS.items():
            s = lab9.stats(r, a, b, d)
            rec[wn] = s
            if s["n"] >= 3:
                print(f"   {wn:26}: {s['n']:5} trades {s['R']:+.3f}R (t {s['t']:5.2f}) win {s['win']:4.1f}% | EUR 1,000 at 0.5%: "
                      f"{s['eur_0.5%']:>6,} (drop {s['dd_0.5%']:.0f}%) | at 2%: {s['eur_2.0%']:>7,} (drop {s['dd_2.0%']:.0f}%)")
        rep[f"NASDAQ {name}"] = rec
    del days, prof
    gc.collect()
    days, prof = prepare("US500m")
    for model, name in chosen.items():
        m = next(x for x in menu() if x[3] == name)
        d, r, rr = trades(days, prof, m[0], m[1], m[2])
        rec = {"design_R": round(float(r[d < cut].mean()), 3), "holdout_R": round(float(r[d >= cut].mean()), 3)}
        print(f"\nS&P 500 cross-check, {name}: 2016-21 {rec['design_R']:+.3f}R | 2022-26 {rec['holdout_R']:+.3f}R")
        for wn, (a, b) in lab9.WINDOWS.items():
            s = lab9.stats(r, a, b, d)
            rec[wn] = s
            if s["n"] >= 3:
                print(f"   {wn:26}: {s['n']:5} trades {s['R']:+.3f}R (t {s['t']:5.2f}) | EUR 1,000 at 0.5%: {s['eur_0.5%']:>6,} | at 2%: {s['eur_2.0%']:>7,}")
        rep[f"S&P {name}"] = rec
    (HERE / "improve_results.json").write_text(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
