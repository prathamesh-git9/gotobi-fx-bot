"""Frozen edge hunt. Reads only the files named in TASK.md; writes results.json.

Run: python research.py
"""
import gc, json, math, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.stats import t as student_t
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(r'E:/Projects/New folder/liquidity_sweep/data')
START, END = pd.Timestamp('2016-10-01'), pd.Timestamp('2026-10-01')
RECENT, HOLD = pd.Timestamp('2024-10-01'), pd.Timestamp('2022-01-01')
SYMS = ['EURUSD','GBPUSD','USDJPY','XAUUSD','USTEC','US500','DE30']
RNG = np.random.default_rng(1729)
TRADES, MAP, ML, ERRORS = [], [], [], []

def read_symbol(sym):
    fs = []
    if sym in ('EURUSD','GBPUSD','USDJPY'):
        fs.append(ROOT / f'{sym}m_2016_m1.parquet')
    if sym == 'XAUUSD': fs.append(ROOT / 'XAUUSDm_2015_m1.parquet')
    fs.append(ROOT / f'{sym}m_m1.parquet')
    cols = ['bopen','bhigh','blow','bclose','aopen','ahigh','alow','aclose','n']
    parts=[]
    for f in fs:
        x=pd.read_parquet(f,columns=cols)
        x.index=pd.to_datetime(x.index,utc=True).tz_localize(None)
        x=x[(x.index>=pd.Timestamp('2015-01-01'))&(x.index<END)]
        parts.append(x)
    x=pd.concat(parts).sort_index()
    x=x[~x.index.duplicated(keep='last')]
    return x

def agg(x, freq, minimum):
    a={c:('first' if c.endswith('open') else 'last' if c.endswith('close') else 'max' if c.endswith('high') else 'min') for c in x.columns if c!='n'}
    a['n']='sum'
    y=x.resample(freq).agg(a)
    y['count']=x.bopen.resample(freq).count()
    y=y[y['count']>=minimum]
    return y

def midcol(y,c): return (y['b'+c]+y['a'+c])/2

def atr(y,n=14):
    h,l,c=midcol(y,'high'),midcol(y,'low'),midcol(y,'close')
    return pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1).rolling(n,min_periods=n).mean().shift(1)

def tval(x):
    x=np.asarray(x,dtype=float); x=x[np.isfinite(x)]
    return float(x.mean()/(x.std(ddof=1)/np.sqrt(len(x)))) if len(x)>1 and x.std(ddof=1)>0 else 0.0

def metric(x):
    x=np.asarray(x,dtype=float); x=x[np.isfinite(x)]
    if not len(x): return dict(n=0,mean=None,t=None,win=None,final=1000.,dd=0.)
    equity=1000*np.cumprod(np.maximum(0,1+0.02*x))
    peak=np.maximum.accumulate(np.r_[1000,equity])[1:]
    return dict(n=int(len(x)),mean=float(x.mean()),t=tval(x),win=float((x>0).mean()),final=float(equity[-1]),dd=float(np.max(1-equity/peak)))

def score_one(bopen,bhigh,blow,aopen,ahigh,alow,entry,exit_i,direction,dist,slip):
    ep=(aopen[entry]+slip) if direction>0 else (bopen[entry]-slip)
    stop=ep-direction*dist
    last=min(exit_i,len(bopen)-1)
    for k in range(entry,last):
        if direction>0 and blow[k]<=stop:
            xp=min(bopen[k]-slip,stop)
            return (xp-ep)/dist,k
        if direction<0 and ahigh[k]>=stop:
            xp=max(aopen[k]+slip,stop)
            return (ep-xp)/dist,k
    xp=(bopen[last]-slip) if direction>0 else (aopen[last]+slip)
    return direction*(xp-ep)/dist,last

def execute(sym,rule,y,signals,horizon,slip=0.,max_gap=None):
    """signals=(signal bar index, direction, stop distance, optional exit bar)."""
    cols=[y[c].to_numpy() for c in ('bopen','bhigh','blow','aopen','ahigh','alow')]
    dates=y.index.to_numpy()
    busy=-1
    for sig,d,dst,*extra in signals:
        e=int(sig)+1
        if e<=busy or e>=len(y) or not np.isfinite(dst) or dst<=0: continue
        z=int(extra[0]) if extra else e+horizon
        if z>=len(y) or z<=e: continue
        if dates[e]<np.datetime64(START) or dates[e]>=np.datetime64(END): continue
        if max_gap is not None:
            if dates[e]-dates[sig]>np.timedelta64(max_gap,'m'):continue
            if dates[z]-dates[e]>np.timedelta64(max_gap*horizon,'m'):continue
        trade_slip=float(slip[e]) if np.ndim(slip) else float(slip)
        r,actual=score_one(*cols,e,z,int(d),float(dst),trade_slip)
        rd=int(RNG.choice([-1,1]))
        rr,_=score_one(*cols,e,z,rd,float(dst),trade_slip)
        busy=actual
        TRADES.append(dict(symbol=sym,rule=rule,date=str(pd.Timestamp(dates[e])),r=float(r),random=float(rr),days=float((dates[actual]-dates[e])/np.timedelta64(1,'D')),dist=float(dst),price=float((cols[0][e]+cols[3][e])/2)))

def daily_rules(sym,m):
    y=agg(m,'1D',60)
    if len(y)<210:return
    h,l,c,o=[midcol(y,z) for z in ('high','low','close','open')]
    ar=atr(y); ranges=h-l; n=len(y)
    base=pd.DataFrame({'h':h,'l':l,'c':c,'o':o,'atr':ar})
    specs={}
    hi20=h.shift(1).rolling(20).max();lo20=l.shift(1).rolling(20).min()
    specs['TurtleSoup']=np.where((h>hi20)&(c<hi20),-1,np.where((l<lo20)&(c>lo20),1,0))
    ma200=c.rolling(200).mean(); ma50=c.rolling(50).mean()
    if sym in ('US500','USTEC','DE30','XAUUSD'):
        specs['Pullback']=np.where((c>ma200)&(l<=l.rolling(3).min()),1,0)
    for name,d in specs.items():
        horizon=3 if name=='TurtleSoup' else 5
        begin=200 if name=='Pullback' else 30
        sig=[(i,int(d[i]),float(ar.iloc[i])) for i in range(begin,n-1) if d[i] and np.isfinite(ar.iloc[i])]
        execute(sym,name,y,sig,horizon)
    for period,opposite in ((20,10),(55,20)):
        up=h.shift(1).rolling(period).max();dn=l.shift(1).rolling(period).min()
        revup=h.shift(1).rolling(opposite).max();revdn=l.shift(1).rolling(opposite).min()
        d=np.where(c>up,1,np.where(c<dn,-1,0))
        sig=[]
        for i in range(200,n-2):
            if not d[i]:continue
            z=min(i+61,n-1)
            for k in range(i+1,z):
                if (d[i]>0 and c.iloc[k]<revdn.iloc[k]) or (d[i]<0 and c.iloc[k]>revup.iloc[k]):z=k+1;break
            sig.append((i,int(d[i]),float(2*ar.iloc[i]),z))
        execute(sym,f'Donchian{period}',y,sig,60)
    d=np.where(ma50>ma200,1,-1)
    sig=[]
    for i in range(200,n-2):
        z=min(i+61,n-1)
        for k in range(i+1,z):
            if d[k]!=d[i]:z=k+1;break
        sig.append((i,int(d[i]),float(2*ar.iloc[i]),z))
    execute(sym,'MA50_200',y,sig,60)
    del y;gc.collect()

def classic_intraday(sym,m):
    y=agg(m,'1D',60)
    h=midcol(y,'high');l=midcol(y,'low');ranges=h-l;ar=atr(y)
    flags={
        'NR4':ranges.shift(1)<ranges.shift(2).rolling(3,min_periods=3).min(),
        'NR7':ranges.shift(1)<ranges.shift(2).rolling(6,min_periods=6).min(),
        'Inside':(h.shift(1)<h.shift(2))&(l.shift(1)>l.shift(2)),
        'Williams':pd.Series(True,index=y.index),
    }
    mh=midcol(m,'high').to_numpy();ml=midcol(m,'low').to_numpy()
    mo=midcol(m,'open').to_numpy()
    sets={k:[] for k in flags}
    groups=m.groupby(m.index.normalize(),sort=True).indices
    for day,pos in groups.items():
        if day not in y.index or day<START or day>=END or len(pos)<3:continue
        j=y.index.get_loc(day)
        if j<30 or not np.isfinite(ar.iloc[j]):continue
        last=pos[-1]
        scan=pos[:-2]
        if len(scan)==0:continue
        for name,eligible in flags.items():
            if not eligible.iloc[j]:continue
            if name=='Williams':
                upper=mo[pos[0]]+0.5*ranges.iloc[j-1]
                lower=mo[pos[0]]-0.5*ranges.iloc[j-1]
            else:
                upper=h.iloc[j-1];lower=l.iloc[j-1]
            ups=mh[scan]>upper;downs=ml[scan]<lower
            hit=np.flatnonzero(ups|downs)
            if len(hit)==0:continue
            k=hit[0]
            if ups[k] and downs[k]:continue
            direction=1 if ups[k] else -1
            sets[name].append((int(scan[k]),direction,float(ar.iloc[j]),int(last)))
    for name,sig in sets.items():execute(sym,name,m,sig,1,max_gap=None)
    del y,mh,ml,mo,groups;gc.collect()

def london(sym,m):
    if sym not in ('EURUSD','GBPUSD','XAUUSD','DE30'):return
    # Thirty-minute compression preserves the fixed 15-minute trigger only in the signal window.
    q=m.between_time('00:00','16:05')
    midc=midcol(q,'close')
    q=q.assign(mc=midc, mh=midcol(q,'high'),ml=midcol(q,'low'))
    sig=[]
    for day,g in q.groupby(q.index.normalize(),sort=True):
        asian=g.between_time('00:00','06:59')
        if len(asian)<240:continue
        hi=asian.mh.max();lo=asian.ml.min();span=hi-lo
        if not np.isfinite(span) or span<=0:continue
        s=g.between_time('07:00','09:59').resample('15min').agg({'mc':'last','bopen':'count'})
        s=s[s.bopen>=10]
        hit=s[(s.mc>hi)|(s.mc<lo)]
        if hit.empty:continue
        t=hit.index[0]+pd.Timedelta(minutes=14)
        loc=m.index.searchsorted(t)
        if loc>=len(m)-1:continue
        direction=1 if hit.mc.iloc[0]>hi else -1
        z=m.index.searchsorted(day+pd.Timedelta(hours=16))
        if z>=len(m) or z<=loc+1:continue
        sig.append((loc,direction,span/2,z))
    execute(sym,'LondonAsian',m,sig,1,max_gap=None)
    del q;gc.collect()

def bh(p,q=.05):
    p=np.asarray(p); rank=np.argsort(p); cutoff=0.
    for j,idx in enumerate(rank,1):
        if p[idx]<=q*j/len(p):cutoff=p[idx]
    return p<=cutoff if cutoff else np.zeros(len(p),bool)

def seasonality(sym,m):
    y=agg(m,'1h',1)
    a=atr(y,14); dates=y.index
    signals=[]
    for i in range(15,len(y)-2):
        if dates[i]<START or dates[i]>=END or not np.isfinite(a.iloc[i]):continue
        if dates[i+1]-dates[i]==pd.Timedelta(hours=1):
            signals.append(('hour',int(dates[i].hour),i,a.iloc[i],i+1))
    # Weekday: first observed quote each UTC date, exit at next date's first quote.
    first=np.flatnonzero(np.r_[True,dates.normalize().to_numpy()[1:]!=dates.normalize().to_numpy()[:-1]])
    for j,i in enumerate(first[:-1]):
        z=first[j+1]
        if dates[i].weekday()<5 and (dates[z]-dates[i])<=pd.Timedelta(hours=36) and i>=15 and np.isfinite(a.iloc[i]):
            signals.append(('weekday',int(dates[i].weekday()),int(i),float(a.iloc[i]),int(z)))
    cols=[y[c].to_numpy() for c in ('bopen','bhigh','blow','aopen','ahigh','alow')]
    for typ,cell,i,dist,z in signals:
        if dates[i]<START:continue
        r,_=score_one(*cols,i,z,1,float(dist),0.)
        rn,_=score_one(*cols,i,z,-1,float(dist),0.)
        MAP.append(dict(symbol=sym,type=typ,cell=cell,date=str(dates[i]),long=float(r),short=float(rn)))
    del y;gc.collect()

def scalp(sym,m):
    x=m[(m.index>=pd.Timestamp('2024-10-01'))&(m.index<END)]
    if x.empty:return
    c=midcol(x,'close');h=midcol(x,'high');l=midcol(x,'low')
    ret=c.diff(); sd=ret.rolling(60,min_periods=60).std().shift(1)
    nmean=x.n.rolling(60,min_periods=60).mean().shift(1)
    rh=h.shift(1).rolling(30,min_periods=30).max();rl=l.shift(1).rolling(30,min_periods=30).min()
    move=ret.abs().rolling(60,min_periods=60).mean().shift(1)
    contiguous=(x.index.to_series().diff()==pd.Timedelta(minutes=1)).to_numpy()
    spread=(x.aopen-x.bopen).to_numpy();dates=x.index
    ny=dates.tz_localize('UTC').tz_convert('America/New_York')
    mins=ny.hour*60+ny.minute
    conds={
        'ExtremeFade':np.where(ret>2*sd,-1,np.where(ret< -2*sd,1,0)),
        'TickBurst':np.where((x.n>2*nmean)&(ret>0),1,np.where((x.n>2*nmean)&(ret<0),-1,0)),
        'MicroBreak30':np.where(c>rh,1,np.where(c<rl,-1,0)),
        'AfterHour':np.where((dates.minute<3)&(ret>0),1,np.where((dates.minute<3)&(ret<0),-1,0)),
        'CashOpen':np.where((mins>=570)&(mins<575)&(ret>0),1,np.where((mins>=570)&(mins<575)&(ret<0),-1,0)),
    }
    # 0.2 bp per side for indices and gold, 0.1 pip for EURUSD.
    slip=0.00001 if sym=='EURUSD' else 0.
    for name,d in conds.items():
        ix=np.flatnonzero((d!=0)&contiguous&np.isfinite(move.to_numpy()))
        fixed_hold={'ExtremeFade':3,'TickBurst':5,'MicroBreak30':15,'AfterHour':1,'CashOpen':5}[name]
        for hold in (fixed_hold,):
            sig=[];last=-100
            for i in ix:
                if i-last<15 or i+1+hold>=len(x):continue
                if dates[i+1+hold]-dates[i+1]!=pd.Timedelta(minutes=hold):continue
                sl=(0.00002 if sym=='EURUSD' else float(c.iloc[i])*0.00004)
                dst=max(float(move.iloc[i])*np.sqrt(hold),2*(spread[i]+sl))
                sig.append((int(i),int(d[i]),dst));last=i
            actual_slip=slip if sym=='EURUSD' else 0.00002*c.to_numpy()
            execute(sym,f'{name}_{hold}m',x,sig,hold,slip=actual_slip,max_gap=2)
    del x;gc.collect()

def ml_rules(sym,m):
    y=agg(m,'1h',1)
    c=midcol(y,'close');h=midcol(y,'high');l=midcol(y,'low')
    v=np.log(c).diff(); ar=atr(y,24)
    feat=pd.DataFrame(index=y.index)
    for k in (1,3,6,24):feat[f'r{k}']=np.log(c/c.shift(k))
    feat['vol24']=v.rolling(24).std()
    hi=h.shift(1).rolling(24).max();lo=l.shift(1).rolling(24).min()
    feat['pos24']=(c-lo)/(hi-lo).replace(0,np.nan)
    for k in (24,120):feat[f'ma{k}']=c/c.rolling(k).mean()-1
    feat['activity']=y.n/y.n.rolling(24).mean().replace(0,np.nan)
    feat['hour']=y.index.hour;feat['weekday']=y.index.weekday
    feat=feat.replace([np.inf,-np.inf],np.nan)
    for horizon in (1,24):
        target=(c.shift(-horizon)>c).astype(int)
        starts=[]
        for year in range(2017 if sym not in ('USTEC','US500','DE30') else 2020,2027):
            cutoff=pd.Timestamp(f'{year}-01-01'); finish=pd.Timestamp(f'{year+1}-01-01')
            train=(feat.index<cutoff-pd.Timedelta(hours=horizon))&(feat.index>=START-pd.Timedelta(days=366))
            # Expanding history, all available earlier data after first valid feature.
            train=(feat.index<cutoff-pd.Timedelta(hours=horizon))&(feat.index>=pd.Timestamp('2016-10-01' if sym not in ('USTEC','US500','DE30') else '2019-08-01'))
            test=(feat.index>=cutoff)&(feat.index<finish)&(feat.index<END)
            if train.sum()<2000 or test.sum()==0:continue
            model=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=15,l2_regularization=1,random_state=1729)
            model.fit(feat.loc[train].to_numpy(),target.loc[train].to_numpy())
            pr=model.predict_proba(feat.loc[test].to_numpy())[:,1]
            inds=np.flatnonzero(test)
            d=np.where(pr>=.55,1,np.where(pr<=.45,-1,0))
            sig=[]
            for i,di in zip(inds,d):
                if di and i+horizon+1<len(y) and np.isfinite(ar.iloc[i]):
                    sig.append((int(i),int(di),float(ar.iloc[i])*(2 if horizon==24 else 1)))
            before=len(TRADES)
            execute(sym,f'ML_{horizon}h',y,sig,horizon,max_gap=120)
            ML.append(dict(symbol=sym,horizon=horizon,year=year,train=int(train.sum()),signals=len(TRADES)-before))
            print('ML',sym,horizon,year,'trades',len(TRADES)-before,flush=True)
    del y;gc.collect()

def add_selected_seasonality():
    mp=pd.DataFrame(MAP)
    mp['date']=pd.to_datetime(mp.date)
    design=mp[mp.date<HOLD]
    options=[]
    for (sym,typ,cell),g in design.groupby(['symbol','type','cell']):
        long=g.long.to_numpy();short=g.short.to_numpy()
        direction=1 if long.mean()>=short.mean() else -1
        v=long if direction==1 else short
        p=float(student_t.sf(tval(v),max(len(v)-1,1))) if len(v)>1 else 1.
        options.append((sym,typ,cell,direction,float(v.mean()),p))
    flags=bh([x[-1] for x in options])
    selected=[x for x,f in zip(options,flags) if f and x[4]>0]
    print('B SELECTED',selected,flush=True)
    for sym,typ,cell,d,_,_ in selected:
        g=mp[(mp.symbol==sym)&(mp.type==typ)&(mp.cell==cell)]
        for row in g.itertuples():
            rd=int(RNG.choice([-1,1]))
            r=row.long if d==1 else row.short
            rr=row.long if rd==1 else row.short
            TRADES.append(dict(symbol=sym,rule='SeasonHour' if typ=='hour' else 'SeasonWeekday',date=str(row.date),r=float(r),random=float(rr),days=0.,dist=1.,price=1.))
    del mp;gc.collect()

def summarize():
    t=pd.DataFrame(TRADES); t['date']=pd.to_datetime(t.date)
    out=[]
    for (rule,sym),g in t.groupby(['rule','symbol'],sort=True):
        for window,cut in [('full',START),('holdout',HOLD),('recent',RECENT)]:
            z=g[g.date>=cut].sort_values('date')
            m=metric(z.r);mr=metric(z.random)
            delta=z.r.to_numpy()-z.random.to_numpy()
            p=float(student_t.sf(tval(delta),max(len(delta)-1,1))) if len(delta)>1 else 1.
            out.append(dict(rule=rule,symbol=sym,window=window,**m,random_mean=mr['mean'],paired_t=tval(delta),paired_p=p))
    res=pd.DataFrame(out)
    # Pooled rows: all symbol trades sorted in time, separate independent rule accounts.
    for rule,g in t.groupby('rule',sort=True):
        for window,cut in [('full',START),('holdout',HOLD),('recent',RECENT)]:
            z=g[g.date>=cut].sort_values(['date','symbol'])
            m=metric(z.r);mr=metric(z.random);delta=z.r.to_numpy()-z.random.to_numpy()
            p=float(student_t.sf(tval(delta),max(len(delta)-1,1))) if len(delta)>1 else 1.
            res.loc[len(res)]=dict(rule=rule,symbol='ALL',window=window,**m,random_mean=mr['mean'],paired_t=tval(delta),paired_p=p)
    # Financing sensitivity applies only to trend rules, at 1 bp notional per calendar day.
    fin=[]
    for rule in ('Donchian20','Donchian55','MA50_200'):
        for window,cut in [('full',START),('holdout',HOLD),('recent',RECENT)]:
            g=t[(t.rule==rule)&(t.date>=cut)]
            debit=.0001*g.price*g.days/g.dist
            fin.append(dict(rule=rule,window=window,**metric(g.r-debit)))
    mp=pd.DataFrame(MAP);mp['date']=pd.to_datetime(mp.date)
    cells=[]
    for (sym,typ,cell),g in mp.groupby(['symbol','type','cell']):
        gd=g[g.date<HOLD]
        direction=1 if gd.long.mean()>=gd.short.mean() else -1
        for window,mask in [('design',g.date<HOLD),('holdout',g.date>=HOLD),('recent',g.date>=RECENT)]:
            z=g[mask];lr=z.long.to_numpy();sr=z.short.to_numpy()
            if not len(z):continue
            v=lr if direction==1 else sr
            # One-sided positive-mean test. Negative spread-driven cells must not ease selection.
            p=float(student_t.sf(tval(v),max(len(v)-1,1))) if len(v)>1 else 1.
            cells.append(dict(symbol=sym,type=typ,cell=int(cell),window=window,direction=direction,n=len(v),mean=float(v.mean()),t=tval(v),p=p,long_mean=float(lr.mean()),short_mean=float(sr.mean())))
    cells=pd.DataFrame(cells)
    des=cells[cells.window=='design'].copy();selected=bh(des.p.to_numpy())&(des['mean'].to_numpy()>0)
    des['selected']=selected
    keys=set(tuple(r) for r in des.loc[selected,['symbol','type','cell','direction']].itertuples(index=False,name=None))
    cells['selected']=cells.apply(lambda r:(r.symbol,r.type,r.cell,r.direction) in keys,axis=1)
    # Post-selection B actual trades are computed separately from MAP entries.
    result={'trades':TRADES,'summary':res.to_dict('records'),'financing':fin,'seasonality':cells.to_dict('records'),'ml_fits':ML,'errors':ERRORS}
    Path('results.json').write_text(json.dumps(result,allow_nan=False),encoding='utf-8')

def main():
    for sym in SYMS:
        print('READ',sym,flush=True)
        m=read_symbol(sym)
        print('BARS',len(m),str(m.index.min()),str(m.index.max()),flush=True)
        daily_rules(sym,m)
        print('DAILY',sym,len(TRADES),flush=True)
        classic_intraday(sym,m)
        print('CLASSIC',sym,len(TRADES),flush=True)
        london(sym,m)
        print('LONDON',sym,len(TRADES),flush=True)
        seasonality(sym,m)
        print('SEASON',sym,len(MAP),flush=True)
        if sym in ('EURUSD','XAUUSD','USTEC','US500'):
            scalp(sym,m)
            print('SCALP',sym,len(TRADES),flush=True)
        ml_rules(sym,m)
        del m;gc.collect()
        # Hold all design cells until global FDR selection is possible.
    add_selected_seasonality()
    summarize()
    print('DONE',len(TRADES),len(MAP),flush=True)

if __name__=='__main__':main()
