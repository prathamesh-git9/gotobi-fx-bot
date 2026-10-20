"""Turn the frozen run into compact audit tables and multiplicity diagnostics."""
import json
import pandas as pd
import numpy as np
from scipy.stats import t as student_t

from research import metric, tval

data=json.load(open('results.json',encoding='utf-8'))
summary=pd.DataFrame(data['summary'])
season=pd.DataFrame(data['seasonality'])
trades=pd.DataFrame(data['trades'])
trades.date=pd.to_datetime(trades.date)

scalp=trades[trades.rule.str.endswith(('1m','3m','5m','15m'))].copy()
rows=[]
for (rule,sym),g in scalp.groupby(['rule','symbol']):
    for window,cut in [('design','2024-10-01'),('test','2025-10-01')]:
        z=g[(g.date>=cut)&(g.date<('2025-10-01' if window=='design' else '2026-10-01'))]
        m=metric(z.r);d=z.r.to_numpy()-z.random.to_numpy()
        rows.append(dict(rule=rule,symbol=sym,window=window,**m,random_mean=metric(z.random)['mean'],paired_t=tval(d),paired_p=float(student_t.sf(tval(d),max(len(d)-1,1))) if len(d)>1 else 1.))
for rule,g in scalp.groupby('rule'):
    for window,cut in [('design','2024-10-01'),('test','2025-10-01')]:
        z=g[(g.date>=cut)&(g.date<('2025-10-01' if window=='design' else '2026-10-01'))].sort_values(['date','symbol'])
        m=metric(z.r);d=z.r.to_numpy()-z.random.to_numpy()
        rows.append(dict(rule=rule,symbol='ALL',window=window,**m,random_mean=metric(z.random)['mean'],paired_t=tval(d),paired_p=float(student_t.sf(tval(d),max(len(d)-1,1))) if len(d)>1 else 1.))
scalp_results=pd.DataFrame(rows)

mtests=int(len(summary[(summary.window=='holdout')&(summary.symbol!='ALL')])+len(season[season.window=='design']))
summary['positive_p']=summary.apply(lambda r:float(student_t.sf(r.t,max(r.n-1,1))) if r.n>1 else 1.,axis=1)
summary['bonf_positive']=np.minimum(1,summary.positive_p*mtests)
summary['bonf_random']=np.minimum(1,summary.paired_p*mtests)
scalp_results['positive_p']=scalp_results.apply(lambda r:float(student_t.sf(r.t,max(r.n-1,1))) if r.n>1 else 1.,axis=1)
scalp_results['bonf_positive']=np.minimum(1,scalp_results.positive_p*mtests)
scalp_results['bonf_random']=np.minimum(1,scalp_results.paired_p*mtests)
summary.to_csv('summary.csv',index=False)
season.to_csv('seasonality.csv',index=False)
scalp_results.to_csv('scalp_split.csv',index=False)
fin=pd.DataFrame(data['financing'])
extra=[]
for symbol in ('ALL','XAUUSD'):
    for window,cut in [('full','2016-10-01'),('holdout','2022-01-01'),('recent','2024-10-01')]:
        z=trades[(trades.rule=='Pullback')&(trades.date>=cut)]
        if symbol!='ALL':z=z[z.symbol==symbol]
        debit=.0001*z.price*z.days/z.dist
        extra.append(dict(rule='Pullback'+(' '+symbol if symbol!='ALL' else ''),window=window,**metric(z.r-debit)))
fin=pd.concat([fin,pd.DataFrame(extra)],ignore_index=True)
fin.to_csv('financing.csv',index=False)

print('TRADES',len(trades),'B MAP',len(season),'MULTIPLICITY',mtests)
print('B SELECTED')
print(season[(season.window=='design')&season.selected][['symbol','type','cell','direction','n','mean','t','p']].to_string(index=False))
print('TOP HOLDOUT BY PAIRED T')
print(summary[(summary.window=='holdout')&(summary.symbol!='ALL')&(summary['mean']>0)].sort_values('paired_t',ascending=False).head(20)[['rule','symbol','n','mean','t','random_mean','paired_t','bonf_positive','bonf_random']].to_string(index=False))
print('TOP SCALP TEST BY PAIRED T')
print(scalp_results[(scalp_results.window=='test')&(scalp_results.symbol!='ALL')&(scalp_results['mean']>0)].sort_values('paired_t',ascending=False).head(20)[['rule','symbol','n','mean','t','random_mean','paired_t','bonf_positive','bonf_random']].to_string(index=False))
print('TREND FINANCING')
print(fin.to_string(index=False))
