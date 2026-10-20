"""Exploratory timing placebo for the XAUUSD 3-day-low pullback, after frozen test."""
import gc,json
from collections import Counter
import numpy as np
import pandas as pd
from research import ROOT,agg,atr,midcol,score_one

fs=[ROOT/'XAUUSDm_2015_m1.parquet',ROOT/'XAUUSDm_m1.parquet']
parts=[]
for f in fs:
    x=pd.read_parquet(f,columns=['bopen','bhigh','blow','bclose','aopen','ahigh','alow','aclose','n'])
    x.index=pd.to_datetime(x.index,utc=True).tz_localize(None)
    parts.append(x[x.index<pd.Timestamp('2026-10-01')])
m=pd.concat(parts).sort_index();m=m[~m.index.duplicated(keep='last')]
y=agg(m,'1D',60);del m,parts;gc.collect()
c=midcol(y,'close');ma200=c.rolling(200).mean();a=atr(y)
eligible=(c>ma200)&a.notna()&(y.index>=pd.Timestamp('2022-01-01'))&(y.index<pd.Timestamp('2026-10-01'))
cols=[y[z].to_numpy() for z in ('bopen','bhigh','blow','aopen','ahigh','alow')]
pool={}
for i in np.flatnonzero(eligible.to_numpy()):
    if i+6>=len(y):continue
    r,_=score_one(*cols,int(i+1),int(i+6),1,float(a.iloc[i]),0.)
    pool.setdefault(y.index[i+1].year,[]).append(r)
data=json.load(open('results.json',encoding='utf-8'))
t=pd.DataFrame(data['trades']);t.date=pd.to_datetime(t.date)
g=t[(t.rule=='Pullback')&(t.symbol=='XAUUSD')&(t.date>=pd.Timestamp('2022-01-01'))]
for name,z in [('holdout',g),('recent',g[g.date>=pd.Timestamp('2024-10-01')])]:
    years=Counter(z.date.dt.year)
    # Match year and trade count. Sampling with replacement permits the same dates
    # and ignores overlap, so this is a timing diagnostic, not a tradable account.
    rng=np.random.default_rng(271828)
    means=[]
    for _ in range(5000):
        v=np.concatenate([rng.choice(pool[year],size=count,replace=True) for year,count in years.items()])
        means.append(float(v.mean()))
    means=np.asarray(means)
    print(name,'rule_n',len(z),'rule_mean',z.r.mean(),'placebo_mean',means.mean(),'placebo_95',np.quantile(means,[.025,.975]),'tail_prob',float((means>=z.r.mean()).mean()))
