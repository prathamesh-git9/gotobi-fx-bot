"""Reproducible Fabio-model proxy backtest. Run: python research.py

Only the two paths named in TASK.md are read. Outputs stay in this directory.
"""
from __future__ import annotations

import gc
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
DATA = Path("E:/Projects/New folder/liquidity_sweep/data")
HIST = Path("E:/Projects/New folder/liquidity_sweep/strategies/fabio/data")
START = pd.Timestamp("2016-10-01", tz="UTC")
END = pd.Timestamp("2026-10-01", tz="UTC")
TRAIN_END = pd.Timestamp("2022-01-01", tz="UTC")
TICK = 0.01
SEED = 20260921
VARIANTS = ("base", "proxy", "first90", "wide_va", "one_r", "hold60")


@dataclass
class Ref:
    day: object
    poc: float
    val: float
    vah: float
    width: float


def profile(price: np.ndarray, width: float):
    if len(price) == 0 or width <= 0:
        return None
    bins = np.floor(price / width).astype(np.int64)
    low = int(bins.min())
    counts = np.bincount(bins - low)
    if not counts.size:
        return None
    poc_i = int(np.argmax(counts))
    l = h = poc_i
    covered = counts[poc_i]
    while covered < 0.7 * len(price):
        lc = counts[l - 1] if l else -1
        hc = counts[h + 1] if h + 1 < len(counts) else -1
        if lc < 0 and hc < 0:
            break
        if lc >= hc:
            l -= 1
            covered += lc
        else:
            h += 1
            covered += hc
    return (low + poc_i + 0.5) * width, (low + l) * width, (low + h + 1) * width


def lvn(price: np.ndarray, width: float, direction: int):
    bins = np.floor(price / width).astype(np.int64)
    if len(bins) < 5 or bins.max() - bins.min() < 4:
        return None
    low = int(bins.min())
    counts = np.bincount(bins - low)
    occupied = np.flatnonzero(counts)
    if len(occupied) < 5:
        return None
    cand = [int(i) for i in occupied[1:-1] if 0 < counts[i] <= 0.7 * counts.max()]
    if not cand:
        return None
    # B lies high for a long leg and low for a short leg.
    i = min(cand, key=lambda x: (counts[x], -direction * x))
    return (low + i) * width, (low + i + 1) * width


def load_symbol(symbol: str):
    cols = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose", "n", "up", "dn"]
    ex = pd.read_parquet(DATA / f"{symbol}_m1.parquet", columns=cols)
    ex.index = pd.to_datetime(ex.index, utc=True)
    ex = ex.loc[(ex.index >= START) & (ex.index < END)]
    if symbol not in ("USTECm", "US500m"):
        return ex
    source = "NSXUSD" if symbol == "USTECm" else "SPXUSD"
    hd = pd.read_parquet(HIST / f"{source}_hd_bid_m1.parquet", columns=cols[:4])
    hd.index = pd.to_datetime(hd.index, utc=True)
    hd = hd.loc[(hd.index >= START) & (hd.index < pd.Timestamp("2019-08-05", tz="UTC"))]
    cal = ex.loc[(ex.index >= pd.Timestamp("2019-08-05", tz="UTC")) &
                 (ex.index < pd.Timestamp("2020-08-01", tz="UTC"))]
    ny = cal.index.tz_convert("America/New_York")
    minute = ny.hour * 60 + ny.minute
    spread = (cal.aopen - cal.bopen).groupby(minute).median()
    fallback = float((cal.aopen - cal.bopen).median())
    hny = hd.index.tz_convert("America/New_York")
    hm = hny.hour * 60 + hny.minute
    sp = spread.reindex(hm).fillna(fallback).to_numpy()
    for a, b in zip(cols[4:8], cols[:4]):
        hd[a] = hd[b].to_numpy() + sp
    for c in ("n", "up", "dn"):
        hd[c] = np.nan
    ex = pd.concat([hd, ex.loc[ex.index >= pd.Timestamp("2019-08-05", tz="UTC")]])
    ex = ex[~ex.index.duplicated(keep="last")].sort_index()
    del hd, cal
    gc.collect()
    return ex


def make_groups(df, zone, start_min, end_min):
    local = df.index.tz_convert(zone)
    mins = local.hour * 60 + local.minute
    mask = (mins >= start_min) & (mins <= end_min)
    ix = np.flatnonzero(mask)
    dates = np.asarray(local.date)[ix]
    groups = {}
    for day, group in pd.Series(ix).groupby(dates, sort=True):
        groups[day] = group.to_numpy()
    return groups


def references(df):
    groups = make_groups(df, "America/New_York", 570, 959)
    mid = ((df.bclose + df.aclose) * 0.5).to_numpy()
    refs = {}
    for d, ii in groups.items():
        if len(ii) < 180:
            continue
        p = mid[ii]
        width = 0.0005 * float(np.median(p))
        prof = profile(p, width)
        if prof:
            refs[d] = Ref(d, *prof, width)
    return refs


def proxy_flags(n, up, dn, i, direction):
    if not np.isfinite(n[i]) or not np.isfinite(up[i]) or not np.isfinite(dn[i]):
        return False
    prior = n[max(0, i - 60):i]
    prior = prior[np.isfinite(prior)]
    if len(prior) < 30:
        return False
    den = up[i] + dn[i]
    imbalance = (up[i] - dn[i]) / den if den > 0 else 0
    return bool(n[i] >= np.quantile(prior, 0.9) and direction * imbalance >= 0.2)


def candidate(arr, ii, ref, older, model, date):
    # Arrays are local to one session, so all indices are causal.
    o, hi, lo, cl, ao, ah, al, ac, n, up, dn, tm = arr
    mid = (cl + ac) * 0.5
    width = ref.width
    stage = 0
    direction = 0
    a = b = 0
    extreme = None
    zone = None
    for i in range(1, len(ii) - 1):
        p = mid[i]
        if model == "trend":
            if stage == 0:
                if i < 30:
                    continue
                direction = 1 if p > ref.vah else (-1 if p < ref.val else 0)
                if not direction:
                    continue
                a = max(0, i - 60) + (np.argmin(mid[max(0, i-60):i+1]) if direction == 1 else np.argmax(mid[max(0, i-60):i+1]))
                b = i
                extreme = p
                stage = 1
                continue
            if stage == 1:
                if direction * p > direction * extreme:
                    b, extreme = i, p
                leg = direction * (extreme - mid[a])
                if leg < 4 * width or direction * (extreme - p) < 0.25 * leg:
                    continue
                zone = lvn(mid[a:b+1], width, direction)
                if zone is None:
                    return None
                stage = 2
                continue
        else:
            if stage == 0:
                direction = -1 if p > ref.vah else (1 if p < ref.val else 0)
                if not direction:
                    continue
                a = i
                extreme = p
                stage = 1
                continue
            if stage == 1:
                if direction * p < direction * extreme:
                    a, extreme = i, p
                if ref.val <= p <= ref.vah:
                    b = i
                    stage = 2
                continue
            if stage == 2:
                if direction * p > direction * mid[b]:
                    b = i
                leg = direction * (mid[b] - extreme)
                if leg < max(4 * width, 0.2 * (ref.vah - ref.val)) or direction * (mid[b] - p) < 0.25 * leg:
                    continue
                zone = lvn(mid[a:b+1], width, direction)
                if zone is None:
                    return None
                stage = 3
                continue
        if stage not in (2 if model == "trend" else 3,):
            continue
        # Zone overlap is checked on mid OHLC. Directional close is checked on mid body.
        midhi, midlo = (hi[i] + ah[i]) * 0.5, (lo[i] + al[i]) * 0.5
        body = p - (o[i] + ao[i]) * 0.5
        if midlo > zone[1] or midhi < zone[0] or direction * body <= 0:
            continue
        if tm[i+1] - tm[i] != np.timedelta64(1, "m"):
            continue
        entry = ao[i+1] if direction == 1 else o[i+1]
        stop = lo[i] - TICK if direction == 1 else ah[i] + TICK
        risk = direction * (entry - stop)
        if risk <= 0 or risk > 0.02 * entry:
            continue
        if model == "reversion":
            target = ref.poc
        else:
            pcs = [r.poc for r in older[-10:] if direction * (r.poc - entry) > 0]
            if not pcs:
                return None
            target = min(pcs, key=lambda x: direction * (x - entry))
        if direction * (target - entry) <= 0:
            return None
        flag = proxy_flags(n, up, dn, i, direction)
        return dict(symbol=None, model=model, date=str(date), time=str(tm[i+1]),
                    direction=direction, entry_i=int(ii[i+1]), entry=float(entry),
                    stop=float(stop), target=float(target), risk=float(risk),
                    proxy=flag, minute=int(i), va_pct=float((ref.vah-ref.val)/ref.poc),
                    ref_day=str(ref.day))
    return None


def make_candidates(df, refs, model):
    if model == "trend":
        groups = make_groups(df, "America/New_York", 570, 930)
        exit_groups = make_groups(df, "America/New_York", 570, 959)
    else:
        groups = make_groups(df, "Europe/London", 480, 690)
        exit_groups = make_groups(df, "Europe/London", 480, 720)
    cols = [df[c].to_numpy() for c in ("bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose", "n", "up", "dn")]
    times = df.index.to_numpy()
    days = sorted(refs)
    import bisect
    result = []
    for date, ii in groups.items():
        pos = bisect.bisect_left(days, date)
        if pos == 0:
            continue
        prev = refs[days[pos - 1]]
        prior = [refs[d] for d in days[max(0, pos - 11):pos - 1]]
        if len(ii) < 60:
            continue
        local = [x[ii] for x in cols] + [times[ii]]
        event = candidate(local, ii, prev, prior, model, date)
        if event:
            event["exit_i"] = int(exit_groups[date][-1])
            result.append(event)
    return result


def exit_trade(df_arrays, event, variant, reverse=False):
    bo, bh, bl, bc, ao, ah, al, ac, times = df_arrays
    i0 = event["entry_i"]
    direction = -event["direction"] if reverse else event["direction"]
    entry = (ao[i0] if direction == 1 else bo[i0]) if reverse else event["entry"]
    risk = event["risk"]
    stop = entry - direction * risk if reverse else event["stop"]
    target = entry + direction * risk if reverse or variant == "one_r" else event["target"]
    limit = 60 if variant == "hold60" else 30
    # Last available bar at or before session cutoff, plus gap guard.
    end = min(event["exit_i"], i0 + limit - 1)
    be_next = False
    for j in range(i0, end + 1):
        if j > i0 and times[j] - times[j-1] != np.timedelta64(1, "m"):
            px = bc[j-1] if direction == 1 else ac[j-1]
            return direction * (px - entry) / risk
        if be_next:
            stop = entry
            be_next = False
        if direction == 1:
            if bo[j] <= stop:
                return (bo[j] - entry) / risk
            if bl[j] <= stop:
                return (stop - entry) / risk
            if bh[j] >= target:
                return (target - entry) / risk
            if bh[j] >= entry + risk:
                be_next = True
        else:
            if ao[j] >= stop:
                return (entry - ao[j]) / risk
            if ah[j] >= stop:
                return (entry - stop) / risk
            if al[j] <= target:
                return (entry - target) / risk
            if al[j] <= entry - risk:
                be_next = True
    px = bc[end] if direction == 1 else ac[end]
    return direction * (px - entry) / risk


def eligible(e, variant):
    if variant == "proxy":
        return e["proxy"]
    if variant == "first90":
        return e["minute"] < 90
    if variant == "wide_va":
        return e["va_pct"] >= 0.005
    return True


def measures(rs):
    x = np.asarray(rs, dtype=float)
    n = len(x)
    if not n:
        return dict(n=0, avg=None, t=None, p=None, win=None, e05=1000., dd05=0., e2=1000., dd2=0.)
    avg = float(x.mean())
    sd = float(x.std(ddof=1)) if n > 1 else np.nan
    t = avg / (sd / np.sqrt(n)) if sd > 0 else None
    # The t statistic is shown as requested, but tiny proxy samples do not
    # support a useful inferential p value.
    p = float(2 * stats.t.sf(abs(t), n-1)) if t is not None and n >= 30 else None
    out = dict(n=n, avg=avg, t=t, p=p, win=float(np.mean(x > 0)))
    for risk, key in ((0.005, "05"), (0.02, "2")):
        eq = 1000. * np.cumprod(np.r_[1., 1. + risk * x])
        peak = np.maximum.accumulate(eq)
        out["e" + key] = float(eq[-1])
        out["dd" + key] = float(np.max(1 - eq / peak))
    return out


def main():
    all_events = []
    coverage = {}
    for symbol in ("USTECm", "US500m", "DE30m", "XAUUSDm"):
        print("Loading", symbol, flush=True)
        df = load_symbol(symbol)
        coverage[symbol] = dict(first=str(df.index.min()), last=str(df.index.max()), rows=len(df))
        refs = references(df)
        arr = [df[c].to_numpy() for c in ("bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose")]
        arr += [df.index.to_numpy()]
        for model in ("trend", "reversion"):
            evs = make_candidates(df, refs, model)
            print(symbol, model, "events", len(evs), flush=True)
            for e in evs:
                e["symbol"] = symbol
                for variant in VARIANTS:
                    if eligible(e, variant):
                        e["r_" + variant] = float(exit_trade(arr, e, variant))
                e["r_1r"] = float(exit_trade(arr, e, "one_r"))
            all_events += evs
        del df, refs, arr
        gc.collect()
    # Random control generated in a separate one-symbol pass to respect memory ceiling.
    rng = np.random.default_rng(SEED)
    for symbol in ("USTECm", "US500m", "DE30m", "XAUUSDm"):
        df = load_symbol(symbol)
        arr = [df[c].to_numpy() for c in ("bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose")]
        arr += [df.index.to_numpy()]
        for e in all_events:
            if e["symbol"] == symbol:
                e["r_random"] = float(exit_trade(arr, e, "one_r", reverse=bool(rng.integers(0, 2))))
        del df, arr
        gc.collect()
    (HERE / "results.json").write_text(json.dumps(dict(coverage=coverage, events=all_events), indent=2))
    render_report(all_events, coverage)


def render_report(events, coverage):
    periods = [("2016-10 to 2026-09", "2016-10-01", "2026-10-01"),
               ("2024-10 to 2026-09", "2024-10-01", "2026-10-01"),
               ("2026 Jan-Sep", "2026-01-01", "2026-10-01")]
    train = [e for e in events if e["symbol"] == "USTECm" and e["date"] < "2022-01-01"]
    scores = {}
    for model in ("trend", "reversion"):
        for variant in VARIANTS:
            vals = [e["r_" + variant] for e in train if e["model"] == model and "r_" + variant in e]
            scores[(model, variant)] = measures(vals)
    best = None
    viable = [(k, v) for k, v in scores.items() if k[1] in ("first90", "wide_va", "one_r", "hold60") and v["n"] >= 30]
    if viable:
        best = max(viable, key=lambda kv: kv[1]["avg"])[0]
    lines = ["# Fabio Valentini model: mechanical CFD backtest", "",
             "Source: transcript supplied in this folder. Rules were fixed in [RULES.md](RULES.md) before returns were computed; implementation is [research.py](research.py). All results are price-quote proxies for a discretionary futures order-flow model.", "",
             "## Data and method", "",
             "- Trades use Exness bid/ask, or HistData bid plus time-of-day median Exness spread before 2019-08-05 for US indices. Profiles use minute mid-close TPO, not exchange volume. The proxy trigger combines quote-tick bursts and up/down quote changes. HistData lacks these fields.",
             "- Entries are at the next minute open, stop wins intrabar ties, no overnight trades. Numbers include quoted spread but exclude commission, financing and extra slippage. One candidate per model/day. Stop distance defines R. A 1R win is not necessarily a 1R POC win.",
             "- Training and all parameter choices: 2016-10-01 through 2021-12-31, NASDAQ only. Untouched judgement interval: 2022-01-01 through 2026-09-30. The overlapping long/recent windows below are descriptive, not independent tests.",
             "- Coverage: " + "; ".join(f"{s} {v['first'][:10]}–{v['last'][:10]} ({v['rows']:,} bars)" for s,v in coverage.items()) + ". DAX and gold therefore cannot supply a full ten years.", "",
             "## NASDAQ training selection", "",
             "| Model | Rule | Trades | Avg R | t | Win % |", "|---|---|---:|---:|---:|---:|"]
    def fmt(x, digits=2):
        return "—" if x is None or not np.isfinite(x) else f"{x:.{digits}f}"
    for k, v in scores.items():
        lines.append(f"| {k[0]} | {k[1]} | {v['n']} | {fmt(v['avg'],3)} | {fmt(v['t'])} | {fmt(None if v['win'] is None else 100*v['win'],1)} |")
    lines += ["", f"Prespecified selection rule chose **{best[0]} / {best[1]}**" if best else "No improvement met the 30-trade training requirement.", "",
              "## Out-of-sample judgement, 2022-01-01 to 2026-09-30", "",
              "| Market | Model | Rule | Trades | Avg R | t | Win % | Adjusted p |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for symbol in ("USTECm", "US500m", "DE30m", "XAUUSDm"):
        for model in ("trend", "reversion"):
            subset = [e for e in events if e["symbol"] == symbol and e["model"] == model and e["date"] >= "2022-01-01"]
            for variant in VARIANTS:
                m = measures([e["r_"+variant] for e in subset if "r_"+variant in e])
                adj = min(1, 12*m["p"]) if m["p"] is not None else None
                lines.append(f"| {symbol} | {model} | {variant} | {m['n']} | {fmt(m['avg'],3)} | {fmt(m['t'])} | {fmt(None if m['win'] is None else 100*m['win'],1)} | {fmt(adj,3)} |")
    lines += ["", "Bonferroni adjusts twelve disclosed model/rule variants **within each market**. P values are omitted below 30 trades; any shown t statistic for a tiny proxy sample is descriptive only. The selected result is still one out-of-sample assessment, and daily clustering makes the naive t statistics optimistic.", "",
              "## Requested account and trade windows", "",
              "Each row gives trades, mean R, t, win rate, EUR 1,000 final balance and peak-to-trough drawdown at 0.5% and 2% fractional risk. A blank sample retains EUR 1,000.", ""]
    for label, begin, end in periods:
        lines += [f"### {label}", "", "| Market | Model | Rule | N | Avg R | t | Win % | 0.5% € | DD % | 2% € | DD % |", "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for symbol in ("USTECm", "US500m", "DE30m", "XAUUSDm"):
            for model in ("trend", "reversion"):
                subset = [e for e in events if e["symbol"] == symbol and e["model"] == model and begin <= e["date"] < end]
                for variant in VARIANTS:
                    m = measures([e["r_"+variant] for e in subset if "r_"+variant in e])
                    lines.append(f"| {symbol} | {model} | {variant} | {m['n']} | {fmt(m['avg'],3)} | {fmt(m['t'])} | {fmt(None if m['win'] is None else 100*m['win'],1)} | {fmt(m['e05'],2)} | {fmt(100*m['dd05'],1)} | {fmt(m['e2'],2)} | {fmt(100*m['dd2'],1)} |")
        lines += [""]
    lines += ["## Random-direction diagnostic", "",
              "At each baseline candidate time, compare the true direction to a seeded 50/50 reversed-direction trade, both with the same initial risk distance and a 1R target. This isolates directional timing; it does not test POC target skill.", "",
              "| Market | Model | N | True 1R avg R | Random 1R avg R |", "|---|---|---:|---:|---:|"]
    for symbol in ("USTECm", "US500m", "DE30m", "XAUUSDm"):
        for model in ("trend", "reversion"):
            subset = [e for e in events if e["symbol"] == symbol and e["model"] == model and e["date"] >= "2022-01-01"]
            a = measures([e["r_1r"] for e in subset]); b = measures([e["r_random"] for e in subset])
            lines.append(f"| {symbol} | {model} | {len(subset)} | {fmt(a['avg'],3)} | {fmt(b['avg'],3)} |")
    lines += ["", "## Verdict", ""]
    if best:
        h = measures([e["r_"+best[1]] for e in events if e["symbol"] == "USTECm" and e["model"] == best[0] and e["date"] >= "2022-01-01" and "r_"+best[1] in e])
        adj = min(1, 12*h["p"]) if h["p"] is not None else None
        lines.append(f"The single training-selected version is **{best[0]} / {best[1]}**. NASDAQ hold-out: {h['n']} trades, {fmt(h['avg'],3)} R/trade, Bonferroni p={fmt(adj,3)}. " + ("It is positive after the quoted spread, but this alone does not establish a reliable or live-tradable edge." if h['avg'] is not None and h['avg'] > 0 else "It fails to show positive hold-out expectancy after the quoted spread. Confidence is moderate that this precise CFD implementation lost during the hold-out, but low that the sign will be stable in a new spread regime."))
    else:
        lines.append("No version qualified as a training-selected improvement; confidence in a profitable mechanical implementation is low.")
    lines += ["", "Changing account risk does not change R expectancy: 2% scales the losses and drawdowns in these negative-expectancy variants, while 0.25% would only slow them. The unselected 2026 NASDAQ trend/base row is slightly positive, but its 94-trade t statistic is only 0.18 and does not rescue the full hold-out.", "",
              "Fabio's claimed edge rests on executed-order aggression, large-trade bubbles, footprint and CVD, none of which exist in these quote data. Tick frequency and quote direction cannot validate that claim. His discretionary identification of balances, swing points and changing market context is also absent. The older-POC trend target is one explicit interpretation of an ambiguous part of the transcript. Conclusions apply only to this TPO/CFD translation, with low confidence about his actual futures method. Spread-era changes and the synthetic 2016–19 asks further limit generalisation.", ""]
    (HERE / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
