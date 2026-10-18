"""Independent USD/JPY gotobi audit. Run `python codex_audit/backtest.py --help`."""
from __future__ import annotations

import argparse
import json
import math
from collections import deque
from pathlib import Path

import holidays
import numpy as np
import pandas as pd

PIP = 0.01
STOP = 0.55
TP = 0.30
FIX = pd.Timedelta(hours=0, minutes=55)
OUT = Path(__file__).resolve().parent


def read_bars(paths):
    cols = ['bopen', 'bhigh', 'blow', 'bclose', 'aopen', 'ahigh', 'alow', 'aclose']
    pieces = [pd.read_parquet(p, columns=cols) for p in paths]
    x = pd.concat(pieces).sort_index(kind='stable')
    x = x[~x.index.duplicated(keep='first')]
    if not x.index.is_monotonic_increasing or x.index.hasnans or (x[cols] <= 0).any().any():
        raise ValueError('Invalid bars or timestamps')
    if ((x.aopen < x.bopen) | (x.aclose < x.bclose) | (x.bhigh < x.blow) |
            (x.ahigh < x.alow)).any():
        raise ValueError('Crossed bid/ask or inverted OHLC range')
    return x


def japan_business(d, jp):
    return d.weekday() < 5 and d not in jp and not (d.month == 12 and d.day == 31) and not (d.month == 1 and d.day <= 3)


def gotobi_dates(start, end):
    jp = holidays.Japan(years=range(start.year - 1, end.year + 2))
    months = pd.period_range((start - pd.Timedelta(days=35)).to_period('M'), end.to_period('M'))
    dates = set()
    for month in months:
        for n in (5, 10, 15, 20, 25, 30):
            try:
                d = pd.Timestamp(month.year, month.month, n)
            except ValueError:
                continue
            while not japan_business(d.date(), jp):
                d -= pd.Timedelta(days=1)
            if start.normalize() <= d <= end.normalize() and (d.month, d.day) not in ((12, 25), (1, 1)):
                dates.add(d)
    return sorted(dates)


def control_dates(start, end, gotobi):
    """Matched yearly and weekday count, fixed seed, from other business dates."""
    jp = holidays.Japan(years=range(start.year, end.year + 2))
    gs = set(gotobi)
    rng = np.random.default_rng(12055)
    result = []
    for year in range(start.year, end.year + 1):
        yd = [d for d in gotobi if d.year == year]
        eligible = [d for d in pd.date_range(max(start, pd.Timestamp(year, 1, 1)), min(end, pd.Timestamp(year, 12, 31)))
                    if d not in gs and japan_business(d.date(), jp) and (d.month, d.day) not in ((12, 25), (1, 1))]
        for wd in range(5):
            k = sum(d.weekday() == wd for d in yd)
            pool = [d for d in eligible if d.weekday() == wd]
            if k and pool:
                result.extend(rng.choice(pool, size=min(k, len(pool)), replace=False).tolist())
    return sorted(pd.Timestamp(d) for d in result)


def quote_at(bars, t, side):
    """At exact minute use open; missing minute uses last observed close."""
    if t in bars.index:
        return float(bars.at[t, side + 'open'])
    i = bars.index.searchsorted(t, side='right') - 1
    if i < 0:
        return np.nan
    return float(bars.iloc[i][side + 'close'])


def tick_month(path, year, month):
    f = Path(path) / f'USDJPYm_{year:04d}_{month:02d}.parquet'
    if not f.exists():
        return None
    x = pd.read_parquet(f, columns=['bid', 'ask'])
    return x.sort_index(kind='stable')


def simulate_day(d, bars, ticks, tp=True, short=True, late=0, extra_cost=0.0):
    out = []
    exit_t = d + pd.Timedelta(minutes=54)
    sched = d - pd.Timedelta(days=1) + pd.Timedelta(hours=15, minutes=55)
    if sched.weekday() == 6:
        # Find the first quoted Sunday evening minute (broker DST is data-derived).
        sunday = bars.loc[d - pd.Timedelta(hours=6):d]
        sunday = sunday[sunday.index.date == sched.date()]
        if len(sunday):
            sched = sunday.index[0] + pd.Timedelta(minutes=15)
    start_i = bars.index.searchsorted(sched)
    limit = min(sched + pd.Timedelta(minutes=120), exit_t - pd.Timedelta(minutes=30))
    entry = None
    entry_t = None
    if sched not in bars.index and sched <= limit:
        stale_bid, stale_ask = quote_at(bars, sched, 'b'), quote_at(bars, sched, 'a')
        if np.isfinite(stale_bid) and np.isfinite(stale_ask) and stale_ask-stale_bid <= 5*PIP+1e-9:
            entry, entry_t = stale_ask, sched
    for i in range(start_i, len(bars)):
        if entry is not None:
            break
        t = bars.index[i]
        if t > limit:
            break
        row = bars.iloc[i]
        if (row.aopen - row.bopen) <= 5 * PIP + 1e-9:
            entry, entry_t = float(row.aopen), t
            break
    if entry is not None:
        stop = entry - STOP
        take = entry + TP
        reason, px, xt = 'time', quote_at(bars, exit_t, 'b'), exit_t
        # The timed exit is at 00:54:00, so no high/low from that minute is observable beforehand.
        segment = bars.loc[entry_t:exit_t - pd.Timedelta(minutes=1)]
        for t, row in segment.iterrows():
            if row.blow <= stop:
                reason, xt, px = 'stop', t, min(stop, float(row.bopen))
                break
            if tp and row.bhigh >= take:
                reason, xt, px = 'take', t, max(take, float(row.bopen))
                break
        if np.isfinite(px):
            out.append(dict(date=d, leg='long', entry_time=entry_t, exit_time=xt,
                            entry_price=entry, exit_price=px, exit_reason=reason,
                            pips=(px-entry)/PIP-extra_cost, R=((px-entry)/PIP-extra_cost)/55))
    if short and ticks is not None:
        fix = d + FIX
        # A long scheduled to exit at 00:54 is flat at the fix, even if it hit a server order earlier.
        target = fix + pd.Timedelta(seconds=late)
        span = ticks.loc[target:fix + pd.Timedelta(minutes=1)]
        if len(span):
            t = span.index[0]
            if late <= 5 and t > fix + pd.Timedelta(seconds=5):
                return out
            bid, ask = float(span.iloc[0].bid), float(span.iloc[0].ask)
            if ask - bid <= 5 * PIP + 1e-9:
                st = bid + STOP
                end = d + pd.Timedelta(hours=1, minutes=25)
                final = ticks.loc[end:end + pd.Timedelta(minutes=1)]
                timed_exit = final.index[0] if len(final) else end
                stream = ticks.loc[t:timed_exit]
                hit = stream[stream.ask >= st]
                if len(hit):
                    xt = hit.index[0]
                    px = max(st, float(hit.iloc[0].ask))
                    reason = 'stop'
                else:
                    if len(final):
                        xt, px = timed_exit, float(final.iloc[0].ask)
                    else:
                        xt, px = end, quote_at(bars, end, 'a')
                    reason = 'time'
                if np.isfinite(px):
                    out.append(dict(date=d, leg='short', entry_time=t, exit_time=xt,
                                    entry_price=bid, exit_price=px, exit_reason=reason,
                                    pips=(bid-px)/PIP-extra_cost, R=((bid-px)/PIP-extra_cost)/55))
    elif short and late == 0:
        # Older Dukascopy data have no ticks. This is an explicitly approximate
        # minute-open fill; it cannot test the five-second execution deadline.
        t = d + FIX
        if t in bars.index:
            bid, ask = float(bars.at[t, 'bopen']), float(bars.at[t, 'aopen'])
            if ask-bid <= 5*PIP+1e-9:
                st = bid + STOP
                end = d + pd.Timedelta(hours=1, minutes=25)
                reason, xt, px = 'time', end, quote_at(bars, end, 'a')
                for bt, row in bars.loc[t:end - pd.Timedelta(minutes=1)].iterrows():
                    if row.ahigh >= st:
                        reason, xt, px = 'stop', bt, max(st, float(row.aopen))
                        break
                if np.isfinite(px):
                    out.append(dict(date=d, leg='short', entry_time=t, exit_time=xt,
                                    entry_price=bid, exit_price=px, exit_reason=reason,
                                    pips=(bid-px)/PIP-extra_cost, R=((bid-px)/PIP-extra_cost)/55))
    return out


def build_trades(bars, dates, ticks_dir=None, tp=True, short=True, late=0, extra_cost=0):
    rows = []
    cache_key, cache = None, None
    for d in dates:
        key = (d.year, d.month)
        if short and ticks_dir and key != cache_key:
            cache = tick_month(ticks_dir, *key)
            cache_key = key
        rows += simulate_day(d, bars, cache if ticks_dir else None, tp, short, late, extra_cost)
    x = pd.DataFrame(rows)
    if len(x):
        x = x.sort_values(['entry_time', 'leg']).reset_index(drop=True)
    return x


def eurusd_at(eur, daily, t):
    if eur is not None and t >= eur.index[0]:
        b = quote_at(eur, t.floor('min'), 'b')
        a = quote_at(eur, t.floor('min'), 'a')
        if np.isfinite(a) and np.isfinite(b):
            return (a+b)/2
    if daily is not None:
        # A daily close stamped with today's date is unavailable intraday.
        i = daily.index.searchsorted(t.normalize(), side='left') - 1
        if i >= 0:
            return float(daily.iloc[i])
    return np.nan


def account(trades, risk=.06, initial=10000., units_step=0., min_units=0., eur=None, daily=None,
            kill=False, start=None, end=None):
    balance = peak = initial
    curve = [initial]
    used = []
    long_r = deque(maxlen=60)
    killed = None
    for row in trades.itertuples(index=False):
        if start is not None and row.date < start:
            continue
        if end is not None and row.date > end:
            continue
        if kill and killed is not None:
            break
        fx_entry = eurusd_at(eur, daily, row.entry_time) if eur is not None or daily is not None else 1.
        fx_exit = eurusd_at(eur, daily, row.exit_time) if eur is not None or daily is not None else 1.
        if not np.isfinite(fx_entry) or not np.isfinite(fx_exit):
            continue
        # Per USD of position, stop loss is 0.55 JPY. Convert that loss at stop USD/JPY.
        stop_px = row.entry_price - STOP if row.leg == 'long' else row.entry_price + STOP
        loss_per_unit_eur = STOP / stop_px / fx_entry
        units = balance*risk/loss_per_unit_eur
        if units_step:
            units = math.floor(units/units_step + 1e-10)*units_step
        if units < min_units:
            continue
        actual_pips = row.pips
        pnl_eur = actual_pips*PIP*units/row.exit_price/fx_exit
        balance += pnl_eur
        peak = max(peak, balance)
        curve.append(balance)
        used.append(dict(date=row.date, leg=row.leg, entry_time=row.entry_time, exit_time=row.exit_time,
                         entry_price=row.entry_price, exit_price=row.exit_price, exit_reason=row.exit_reason,
                         pips=actual_pips, pnl=pnl_eur, R=row.R, units=units, balance=balance))
        if row.leg == 'long':
            long_r.append(row.R)
        if kill and (balance <= 0.5*peak or (len(long_r) == 60 and sum(long_r) < -6)):
            killed = (row.exit_time, 'drawdown' if balance <= 0.5*peak else '60-long R')
    dd = max((1-v/max(curve[:i+1]) for i,v in enumerate(curve)), default=0.)
    return dict(balance=balance, multiple=balance/initial, drawdown=dd, trades=len(used),
                killed=killed, used=pd.DataFrame(used), curve=np.asarray(curve))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', nargs='+', required=True, help='USD/JPY minute parquet files')
    ap.add_argument('--start', default='2016-01-01')
    ap.add_argument('--end', default='2026-10-16')
    ap.add_argument('--risk', type=float, default=.06)
    ap.add_argument('--ticks-dir', default='data/fix_ticks')
    ap.add_argument('--eur-data', nargs='*', default=['data/EURUSDm_m1.parquet','data/EURUSDm_2026_10_m1.parquet'])
    ap.add_argument('--daily', default='data/daily_yahoo.parquet')
    ap.add_argument('--output', default=str(OUT/'trades.csv'))
    ap.add_argument('--audit', action='store_true', help='Run all requested variants and write summary JSON/CSVs')
    args = ap.parse_args()
    if not 0 < args.risk < 1:
        ap.error('--risk must be between 0 and 1')
    start, end = pd.Timestamp(args.start), pd.Timestamp(args.end)
    bars = read_bars(args.data)
    dates = gotobi_dates(start, end)
    full = build_trades(bars, dates, args.ticks_dir)
    eur_paths = [p for p in args.eur_data if Path(p).exists()]
    eur = read_bars(eur_paths) if eur_paths else None
    daily = None
    if Path(args.daily).exists():
        d = pd.read_parquet(args.daily, columns=['date','sym','close'])
        d = d[d.sym == 'EURUSD=X'].set_index('date').close.sort_index()
        daily = d[~d.index.duplicated(keep='last')]
    run = account(full, args.risk, eur=eur, daily=daily, kill=True)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    run['used'].to_csv(args.output, index=False)
    if args.audit:
        audit(bars, dates, full, eur, daily, args)
    print(json.dumps({k:v for k,v in run.items() if k not in ('used','curve')}, default=str, indent=2))


def audit(bars, dates, full, eur, daily, args):
    plain = build_trades(bars, dates, args.ticks_dir, tp=False, short=False)
    short = full[full.leg == 'short'].copy()
    variants = {'plain':plain, 'full':full, 'short':short}
    annual = []
    for year in range(pd.Timestamp(args.start).year, pd.Timestamp(args.end).year+1):
        for name, x in variants.items():
            y = x[x.date.dt.year == year]
            a = account(y, risk=args.risk, eur=eur, daily=daily, kill=False)
            annual.append(dict(year=year, variant=name, trades=a['trades'], win_rate=float((a['used'].pips > 0).mean()) if a['trades'] else None,
                               net_pips=float(a['used'].pips.sum()) if a['trades'] else 0,
                               return_pct=(a['multiple']-1)*100, max_dd_pct=a['drawdown']*100))
    pd.DataFrame(annual).to_csv(OUT/'annual.csv', index=False)
    stats = {'continuous':{}, 'small':{}, 'summary':{}, 'costs':{}, 'late':{}, 'controls':{}}
    for risk in (.03,.06,.10):
        a = account(full, risk=risk, eur=eur, daily=daily, kill=True)
        stats['continuous'][str(risk)] = {k:v for k,v in a.items() if k not in ('used','curve')}
    for begin in ('2025-01-01','2026-01-01'):
        for name, step in (('standard',1000.),('cent',10.)):
            a = account(full, risk=args.risk, initial=100., units_step=step, min_units=step,
                        eur=eur, daily=daily, kill=True, start=pd.Timestamp(begin))
            u = a['used']
            oct26 = u[(u.date >= pd.Timestamp('2026-10-01')) & (u.date <= pd.Timestamp('2026-10-16'))] if len(u) else u
            stats['small'][begin+'_'+name] = dict(balance=a['balance'], drawdown=a['drawdown'], trades=a['trades'],
                                                  october_2026_pnl=float(oct26.pnl.sum()) if len(oct26) else 0,
                                                  october_2026_trades=len(oct26), killed=a['killed'])
            u.to_csv(OUT/f'account_{begin}_{name}.csv',index=False)
    for name,x in variants.items():
        r = x.R.to_numpy()
        if len(r):
            rng = np.random.default_rng(104)
            bs = np.mean(rng.choice(r, (10000,len(r)), replace=True),axis=1)
            blocks = x.groupby('date').agg(total=('R','sum'), n=('R','size'))
            draws = rng.integers(0,len(blocks),size=(5000,len(blocks)))
            block_means = blocks.total.to_numpy()[draws].sum(axis=1)/blocks.n.to_numpy()[draws].sum(axis=1)
            stats['summary'][name] = dict(n=len(r), mean_R=float(r.mean()), t_stat=float(r.mean()/(r.std(ddof=1)/np.sqrt(len(r)))),
                                          ci_R=np.quantile(bs,[.025,.975]).tolist(),
                                          day_block_ci_R=np.quantile(block_means,[.025,.975]).tolist(),
                                          max_losing_streak=max_streak(r))
    for p in (.5,1.,2.):
        r = full.R.to_numpy()-p/55
        stats['costs'][str(p)] = dict(mean_R=float(r.mean()), net_pips=float(full.pips.sum()-p*len(full)))
    for sec in (2,5,10):
        x = build_trades(bars, dates, args.ticks_dir, tp=True, short=True, late=sec)
        s = x[x.leg == 'short']
        stats['late'][str(sec)] = dict(n=len(s), mean_R=float(s.R.mean()) if len(s) else None,
                                       net_pips=float(s.pips.sum()) if len(s) else None)
    controls = build_trades(bars, control_dates(pd.Timestamp(args.start),pd.Timestamp(args.end), dates), args.ticks_dir)
    for name,x in (('full',controls),('long',controls[controls.leg=='long']),('short',controls[controls.leg=='short'])):
        blocks = x.groupby('date').agg(total=('R','sum'), n=('R','size'))
        draws = np.random.default_rng(112).integers(0,len(blocks),size=(5000,len(blocks)))
        means = blocks.total.to_numpy()[draws].sum(axis=1)/blocks.n.to_numpy()[draws].sum(axis=1)
        stats['controls'][name] = dict(n=len(x), mean_R=float(x.R.mean()), net_pips=float(x.pips.sum()),
                                      day_block_ci_R=np.quantile(means,[.025,.975]).tolist())
    for name,x in variants.items():
        stats['summary'][name]['halves'] = []
        med = x.date.sort_values().iloc[len(x)//2]
        for label,mask in (('first',x.date<med),('second',x.date>=med),('2016_2021',x.date.dt.year<=2021),('2022_2026',x.date.dt.year>=2022)):
            y=x[mask]
            stats['summary'][name]['halves'].append(dict(period=label,n=len(y),mean_R=float(y.R.mean()),net_pips=float(y.pips.sum())))
    # Resample complete trade-day blocks to retain dependence between the two legs.
    grouped = [g.R.to_numpy() for _,g in full.groupby('date')]
    rng = np.random.default_rng(613)
    outcomes = []
    for _ in range(10000):
        sample = rng.integers(0,len(grouped),size=len(grouped))
        equity = peak = 1.
        worst = 0.
        for j in sample:
            for r in grouped[j]:
                equity *= 1+.06*r
                peak=max(peak,equity)
                worst=max(worst,1-equity/peak)
        outcomes.append(worst)
    stats['monte_carlo'] = dict(prob_50dd=float(np.mean(np.asarray(outcomes)>=.5)),drawdown_ci=np.quantile(outcomes,[.05,.5,.95]).tolist(),
                                method='10000 iid bootstrap samples of complete trade days over historical length, fixed 6% fractional risk, no kill switch')
    (OUT/'summary.json').write_text(json.dumps(stats,indent=2,default=str),encoding='utf-8')
    plain.to_csv(OUT/'plain_trades.csv',index=False)
    full.to_csv(OUT/'full_unconstrained_trades.csv',index=False)
    controls.to_csv(OUT/'control_trades.csv',index=False)


def max_streak(r):
    best=now=0
    for v in r:
        now = now+1 if v<0 else 0
        best=max(best,now)
    return best


if __name__ == '__main__':
    main()
