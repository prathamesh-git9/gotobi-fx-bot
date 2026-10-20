"""Frozen-rule CFD replication. Run: python research.py (from this folder).

Uses one symbol at a time, M5/M15 bars, real bid/ask, and never reads holdout
statistics to choose a parameter. See RULES.md for the ex ante protocol.
"""
from __future__ import annotations

import gc
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent.parent / "data"
END = pd.Timestamp("2026-10-01")
START = pd.Timestamp("2016-10-01")
RECENT = pd.Timestamp("2024-10-01")
HOLD = pd.Timestamp("2022-01-01")
COLS = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose", "n", "up", "dn"]
AGG = {"bopen":"first", "bhigh":"max", "blow":"min", "bclose":"last",
       "aopen":"first", "ahigh":"max", "alow":"min", "aclose":"last",
       "n":"sum", "up":"sum", "dn":"sum"}
SYMBOLS = ["XAUUSD", "USTEC", "US500", "EURUSD", "GBPUSD", "USDJPY"]
RULES = ["R1_smc_fvg", "R2_sr_retest", "R3_orb", "R4_orb_rvol",
         "R5_noise_vwap", "R6_first_last", "R7_round_cross", "R8_round_fade"]


def load_symbol(symbol):
    files = []
    if symbol == "XAUUSD":
        files.append(DATA / "XAUUSDm_2015_m1.parquet")
    elif symbol in ("EURUSD", "GBPUSD", "USDJPY"):
        files.append(DATA / f"{symbol}m_2016_m1.parquet")
    files.append(DATA / f"{symbol}m_m1.parquet")
    chunks = []
    for p in files:
        x = pd.read_parquet(p, columns=COLS)
        x = x.loc[(x.index >= START - pd.Timedelta(days=30)) & (x.index < END)]
        y = x.resample("5min").agg(AGG).dropna(subset=["bopen", "aopen"])
        chunks.append(y)
        del x, y
        gc.collect()
    d = pd.concat(chunks).sort_index()
    d = d[~d.index.duplicated(keep="last")]
    for name in ("open", "high", "low", "close"):
        d["m"+name] = (d["b"+name] + d["a"+name]) / 2
    d["spread"] = d.aopen - d.bopen
    return d


def m15(d):
    x = d.resample("15min").agg(AGG).dropna(subset=["bopen", "aopen"])
    for n in ("open", "high", "low", "close"):
        x["m"+n] = (x["b"+n]+x["a"+n])/2
    x["spread"] = x.aopen-x.bopen
    return x


def ny_frame(d):
    local = d.index.tz_localize("UTC").tz_convert("America/New_York")
    minutes = local.hour * 60 + local.minute
    mask = (minutes >= 570) & (minutes <= 955) & (local.dayofweek < 5)
    x = d.loc[mask].copy()
    z = local[mask]
    x["day"] = z.date
    x["nymin"] = z.hour * 60 + z.minute
    return x


def daily_atr(us):
    g = us.groupby("day", sort=True)
    daily = pd.DataFrame({"high":g.mhigh.max(), "low":g.mlow.min(),
                          "open":g.mopen.first(), "close":g.mclose.last(),
                          "first_n":g.n.first()})
    prev = daily.close.shift()
    tr = pd.concat([daily.high-daily.low, (daily.high-prev).abs(),
                    (daily.low-prev).abs()], axis=1).max(axis=1)
    daily["atr"] = tr.rolling(14, min_periods=14).mean().shift()
    daily["prev_close"] = prev
    daily["rvol"] = daily.first_n / daily.first_n.rolling(14, min_periods=14).mean().shift()
    return daily


def blank(n):
    return {"direction":np.zeros(n, np.int8), "anchor":np.full(n, np.nan),
            "distance":np.full(n, np.nan), "target_r":np.full(n, np.nan),
            "target_abs":np.full(n, np.nan), "maxbars":np.zeros(n, np.int16),
            "flow":np.full(n, np.nan), "activity":np.full(n, np.nan)}


def smc_signal(d):
    n = len(d); s=blank(n)
    high=d.mhigh.to_numpy(); low=d.mlow.to_numpy(); op=d.mopen.to_numpy(); close=d.mclose.to_numpy()
    prior_hi=pd.Series(high).rolling(20).max().shift().to_numpy()
    prior_lo=pd.Series(low).rolling(20).min().shift().to_numpy()
    body=np.abs(close-op); med=pd.Series(body).rolling(20).median().shift().to_numpy()
    hrs=d.index.hour + d.index.minute/60
    valid=(hrs>=7)&(hrs<=19.75)
    sweep_up=(low<prior_lo)&(close>prior_lo)&valid
    sweep_dn=(high>prior_hi)&(close<prior_hi)&valid
    for i in np.flatnonzero(sweep_up | sweep_dn):
        side=1 if sweep_up[i] else -1
        for j in range(i+1,min(i+3,n)):
            if d.index[j].date()!=d.index[i].date(): break
            gap = low[j]>high[j-2] if side==1 else high[j]<low[j-2]
            if not (gap and body[j]>=1.2*med[j] and (close[j]-op[j])*side>0): continue
            mid=(low[j]+high[j-2])/2 if side==1 else (high[j]+low[j-2])/2
            for k in range(j+1,min(j+5,n)):
                if d.index[k].date()!=d.index[i].date(): break
                touch=low[k]<=mid<=high[k]
                if touch and (close[k]-mid)*side>0 and valid[k] and s["direction"][k]==0:
                    s["direction"][k]=side; s["anchor"][k]=low[i] if side==1 else high[i]
                    s["target_r"][k]=2
                    s["flow"][k]=(d.up.iloc[k]-d.dn.iloc[k])/max(1,d.up.iloc[k]+d.dn.iloc[k])
                    break
            break
    return s


def sr_signal(d):
    n=len(d); s=blank(n)
    high=d.mhigh.to_numpy(); low=d.mlow.to_numpy(); close=d.mclose.to_numpy()
    hi=pd.Series(high).rolling(20).max().shift().to_numpy()
    lo=pd.Series(low).rolling(20).min().shift().to_numpy()
    med=pd.Series(high-low).rolling(20).median().shift().to_numpy()
    hrs=d.index.hour+d.index.minute/60; valid=(hrs>=7)&(hrs<=19.75)
    pos=(close>hi+0.1*med)&valid; neg=(close<lo-0.1*med)&valid
    ns=d.n.to_numpy(); nmed=pd.Series(ns).rolling(20).median().shift().to_numpy()
    up=d.up.to_numpy(); dn=d.dn.to_numpy()
    for i in np.flatnonzero(pos|neg):
        side=1 if pos[i] else -1; level=hi[i] if side==1 else lo[i]
        for k in range(i+1,min(i+5,n)):
            if d.index[k].date()!=d.index[i].date() or pos[k] or neg[k]: break
            touch=low[k]<=level<=high[k]
            if touch and (close[k]-level)*side>0 and valid[k] and s["direction"][k]==0:
                s["direction"][k]=side; s["anchor"][k]=low[k] if side==1 else high[k]
                s["target_r"][k]=2
                s["flow"][k]=(up[i]-dn[i])/max(1,up[i]+dn[i])*side
                s["activity"][k]=ns[i]/nmed[i] if nmed[i]>0 else np.nan
                break
    return s


def orb_signal(us, daily, rvol=False):
    s=blank(len(us)); ix=us.index; mins=us.nymin.to_numpy(); days=us.day.to_numpy()
    op=us.mopen.to_numpy(); cl=us.mclose.to_numpy(); hi=us.mhigh.to_numpy(); lo=us.mlow.to_numpy()
    up=us.up.to_numpy(); dn=us.dn.to_numpy()
    first=np.flatnonzero(mins==570)
    for i in first:
        day=days[i]
        if day not in daily.index: continue
        atr=daily.at[day,"atr"]; rv=daily.at[day,"rvol"]
        if not np.isfinite(atr) or atr<=0 or (rvol and not (rv>=1)): continue
        side=int(np.sign(cl[i]-op[i]))
        if side==0: continue
        for k in range(i+1,min(i+78,len(us))):
            if days[k]!=day or mins[k]>=950: break
            crossed=cl[k]>hi[i] if side==1 else cl[k]<lo[i]
            if crossed:
                s["direction"][k]=side; s["distance"][k]=0.1*atr
                s["flow"][k]=side*(up[i]-dn[i])/max(1,up[i]+dn[i])
                s["activity"][k]=rv
                break
    return s


def noise_signal(us, daily):
    """M30 completed decisions represented on their final M5 bar."""
    s=blank(len(us)); d=us.copy()
    d["move"]=(d.mclose/d.groupby("day").mopen.transform("first")-1).abs()
    # prior 14 sessions at the same end-of-half-hour slot
    slot=d.nymin.to_numpy(); decision=(slot>=595)&(slot<=925)&((slot+5)%30==0)
    d["sigma"]=np.nan
    for t in np.unique(slot[decision]):
        idx=np.flatnonzero(slot==t)
        d.iloc[idx,d.columns.get_loc("sigma")]=d.move.iloc[idx].rolling(14,min_periods=14).mean().shift().to_numpy()
    typical=(d.mhigh+d.mlow+d.mclose)/3
    d["vwap"]=(typical*d.n).groupby(d.day).cumsum()/d.n.groupby(d.day).cumsum().replace(0,np.nan)
    days=d.day.to_numpy(); close=d.mclose.to_numpy(); sigma=d.sigma.to_numpy(); vw=d.vwap.to_numpy()
    for i in np.flatnonzero(decision):
        day=days[i]
        if day not in daily.index: continue
        row=daily.loc[day]; atr=row["atr"]
        if not (np.isfinite(sigma[i]) and np.isfinite(atr) and atr>0): continue
        upper=max(row["open"],row["prev_close"])*(1+sigma[i])
        lower=min(row["open"],row["prev_close"])*(1-sigma[i])
        # desired sign including same-side trailing band/VWAP exit.
        if close[i]>max(upper,vw[i]): side=1
        elif close[i]<min(lower,vw[i]): side=-1
        else: side=0
        s["direction"][i]=side; s["distance"][i]=atr
    s["stateful"]=True
    return s


def gao_signal(us, daily):
    s=blank(len(us)); mins=us.nymin.to_numpy(); days=us.day.to_numpy(); cl=us.mclose.to_numpy()
    # 09:55 close is the first half-hour close; 15:25 bar is decision for 15:30 open.
    for i in np.flatnonzero(mins==925):
        day=days[i]
        if day not in daily.index: continue
        atr=daily.at[day,"atr"]; prev=daily.at[day,"prev_close"]
        if not (np.isfinite(atr) and atr>0 and np.isfinite(prev)): continue
        morning=np.flatnonzero((days==day)&(mins==595))
        if len(morning)!=1: continue
        side=int(np.sign(cl[morning[0]]-prev))
        s["direction"][i]=side; s["distance"][i]=atr
    return s


def round_signal(d, symbol, fade=False, placebo=False):
    n=len(d); s=blank(n); grid=0.5 if symbol=="USDJPY" else 0.005
    offset=grid/2 if placebo else 0
    close=d.mclose.to_numpy(); hi=d.mhigh.to_numpy(); lo=d.mlow.to_numpy()
    hrs=d.index.hour+d.index.minute/60; valid=(hrs>=7)&(hrs<=19.75)
    # crossing and approach assessed against the nearest relevant grid to previous close
    level=np.round((close[:-1]-offset)/grid)*grid+offset
    for i in np.flatnonzero(valid[1:])+1:
        lev=level[i-1]; prior=close[i-1]; now=close[i]
        if not fade:
            side=1 if prior<lev and now>lev else (-1 if prior>lev and now<lev else 0)
            # also check adjacent grid crossed in a large bar
            if not side:
                lev2=(math.floor((prior-offset)/grid)+1)*grid+offset if now>prior else (math.ceil((prior-offset)/grid)-1)*grid+offset
                side=1 if prior<lev2<now else (-1 if now<lev2<prior else 0)
        else:
            side=1 if prior<=lev-grid/4 and lo[i]<=lev and 0<=lev-now<=grid/10 else 0
            if prior>=lev+grid/4 and hi[i]>=lev and 0<=now-lev<=grid/10: side=-1
        if side:
            s["direction"][i]=side; s["distance"][i]=grid/4
            s["target_abs"][i]=grid*(0.5 if fade else 1.0)
            s["maxbars"][i]=6
    return s


def round_price_diagnostic(d, s, symbol):
    """Osler-style 15-minute post-event quote movement, no execution assumptions."""
    grid=0.5 if symbol=="USDJPY" else 0.005
    ids=np.flatnonzero(s["direction"]!=0)
    ids=ids[ids+3<len(d)]
    if len(ids)==0: return []
    close=d.mclose.to_numpy(); day=np.asarray(d.index.date)
    ids=ids[day[ids]==day[ids+3]]
    moved=s["direction"][ids]*(close[ids+3]-close[ids])/grid
    return moved.tolist()


def simulate(d, s, rule, symbol, placebo=False, seed=43):
    """Bid/ask event simulator; time exit always at the next eligible bar open."""
    n=len(d); times=d.index; step=15 if rule in ("R1_smc_fvg","R2_sr_retest") else 5
    arrays={c:d[c].to_numpy() for c in ("bopen","bhigh","blow","bclose","aopen","ahigh","alow","aclose","mopen","spread")}
    ny=("nymin" in d.columns)
    mins=d.nymin.to_numpy() if ny else times.hour.to_numpy()*60+times.minute.to_numpy()
    days=d.day.to_numpy() if ny else np.asarray(times.date)
    lastmin=955 if ny else (1245 if step==15 else 1255)
    candidates=np.flatnonzero(s["direction"]!=0)
    if s.get("stateful"):
        candidates=np.flatnonzero((s["direction"]!=0)&(s["distance"]>0))
    trades=[]; occupied_until=-1; rng=np.random.default_rng(seed)
    for i in candidates:
        j=i+1
        if j>=n or j<=occupied_until or days[j]!=days[i] or times[j]-times[i]!=pd.Timedelta(minutes=step) or mins[j]>=lastmin: continue
        side=int(s["direction"][i])
        if side==0: continue
        entry=arrays["aopen"][j] if side==1 else arrays["bopen"][j]
        if np.isfinite(s["anchor"][i]):
            dist=abs(arrays["mopen"][j]-s["anchor"][i])+arrays["spread"][j]
        else: dist=s["distance"][i]
        if not np.isfinite(dist) or dist<=0: continue
        targetdist=s["target_abs"][i] if np.isfinite(s["target_abs"][i]) else s["target_r"][i]*dist
        if not np.isfinite(targetdist): targetdist=np.nan
        def one(direction):
            en=arrays["aopen"][j] if direction==1 else arrays["bopen"][j]
            stop=en-direction*dist
            target=en+direction*targetdist if np.isfinite(targetdist) else np.nan
            # entry bar can hit the stop; no favorable lookahead.
            end=j; exitpx=np.nan; cause=""
            while end<n:
                if end>j and times[end]-times[end-1]!=pd.Timedelta(minutes=step):
                    end-=1
                    exitpx=arrays["bclose"][end] if direction==1 else arrays["aclose"][end]
                    cause="data_gap"; break
                if days[end]!=days[j]:
                    end-=1
                    exitpx=arrays["bclose"][end] if direction==1 else arrays["aclose"][end]
                    cause="data_end"; break
                if mins[end]>=lastmin or (s["maxbars"][i]>0 and end-j>=s["maxbars"][i]):
                    exitpx=arrays["bopen"][end] if direction==1 else arrays["aopen"][end]
                    cause="time"; break
                if s.get("stateful") and end>j:
                    prev=end-1
                    if s["distance"][prev]>0 and s["direction"][prev]!=direction:
                        exitpx=arrays["bopen"][end] if direction==1 else arrays["aopen"][end]
                        cause="trail"; break
                exopen=arrays["bopen"][end] if direction==1 else arrays["aopen"][end]
                bad=arrays["blow"][end]<=stop if direction==1 else arrays["ahigh"][end]>=stop
                good=(arrays["bhigh"][end]>=target if direction==1 else arrays["alow"][end]<=target) if np.isfinite(target) else False
                if bad:
                    exitpx=min(exopen,stop) if direction==1 else max(exopen,stop)
                    cause="stop"; break
                if good:
                    exitpx=target; cause="target"; break
                end+=1
            if not np.isfinite(exitpx):
                end=n-1; exitpx=arrays["bclose"][end] if direction==1 else arrays["aclose"][end]; cause="data_end"
            return direction*(exitpx-en)/dist,end,cause
        ret,end,cause=one(side)
        rand_dir=int(rng.choice([-1,1])); randret,_,_=one(rand_dir)
        trades.append({"rule":rule,"symbol":symbol,"signal":str(times[i]),"entry":str(times[j]),"exit":str(times[end]),
                       "R":float(ret),"random_R":float(randret),"side":side,"random_side":rand_dir,
                       "cause":cause,"flow":float(s["flow"][i]),"activity":float(s["activity"][i]),"placebo":placebo})
        occupied_until=end
    return trades


def summary(rows):
    if not rows: return {"trades":0,"average_R":None,"t":None,"win_rate":None,"final_eur":1000.0,"max_drawdown":0.0,
                         "random_average_R":None,"paired_t":None,"p_positive":None,"p_vs_random":None}
    rows=sorted(rows,key=lambda r:(r["entry"],SYMBOLS.index(r["symbol"])))
    a=np.asarray([r["R"] for r in rows]); b=np.asarray([r["random_R"] for r in rows]); n=len(a)
    t=float(a.mean()/(a.std(ddof=1)/np.sqrt(n))) if n>1 and a.std(ddof=1)>0 else 0.0
    diff=a-b; pt=float(diff.mean()/(diff.std(ddof=1)/np.sqrt(n))) if n>1 and diff.std(ddof=1)>0 else 0.0
    eq=np.maximum(0,1+0.02*a); balance=1000*np.cumprod(eq); peak=np.maximum.accumulate(np.r_[1000,balance])
    mdd=float(np.max(1-np.r_[1000,balance]/peak))
    return {"trades":n,"average_R":float(a.mean()),"t":t,"win_rate":float(np.mean(a>0)),
            "final_eur":float(balance[-1]),"max_drawdown":mdd,"random_average_R":float(b.mean()),
            "paired_t":pt,"p_positive":float(stats.t.sf(t,n-1)) if n>1 else None,
            "p_vs_random":float(stats.t.sf(pt,n-1)) if n>1 else None}


def one_position_per_rule(rows):
    """Fixed symbol priority breaks simultaneous signal ties; no cross-symbol overlap."""
    selected=[]
    for name in RULES:
        for placebo in (False,True):
            last_exit=""
            batch=sorted((r for r in rows if r["rule"]==name and r["placebo"]==placebo),
                         key=lambda r:(r["entry"],SYMBOLS.index(r["symbol"])))
            for r in batch:
                if r["entry"]>last_exit:
                    selected.append(r)
                    last_exit=r["exit"]
    return selected


def main():
    allrows=[]; coverage={}; round_moves={}
    for symbol in SYMBOLS:
        print("Processing",symbol,flush=True)
        d=load_symbol(symbol)
        coverage[symbol]={"first":str(d.index.min()),"last":str(d.index.max()),"m5_bars":len(d)}
        if symbol in ("XAUUSD","USTEC","US500","EURUSD","GBPUSD"):
            q=m15(d)
            for name,fun in (("R1_smc_fvg",smc_signal),("R2_sr_retest",sr_signal)):
                print(" ",name,flush=True)
                allrows.extend(simulate(q,fun(q),name,symbol,seed=100+RULES.index(name)))
            del q;gc.collect()
        if symbol in ("USTEC","US500"):
            us=ny_frame(d); daily=daily_atr(us)
            if symbol=="USTEC":
                for name,rv in (("R3_orb",False),("R4_orb_rvol",True)):
                    print(" ",name,flush=True)
                    allrows.extend(simulate(us,orb_signal(us,daily,rv),name,symbol,seed=100+RULES.index(name)))
            else:
                for name,fun in (("R5_noise_vwap",noise_signal),("R6_first_last",gao_signal)):
                    print(" ",name,flush=True)
                    allrows.extend(simulate(us,fun(us,daily),name,symbol,seed=100+RULES.index(name)))
            del us,daily;gc.collect()
        if symbol in ("EURUSD","GBPUSD","USDJPY"):
            for name,fade in (("R7_round_cross",False),("R8_round_fade",True)):
                for placebo in (False,True):
                    print(" ",name,"placebo" if placebo else "round",flush=True)
                    sig=round_signal(d,symbol,fade,placebo)
                    round_moves[f"{name}_{symbol}_{'placebo' if placebo else 'round'}"]=round_price_diagnostic(d,sig,symbol)
                    allrows.extend(simulate(d,sig,name,symbol,placebo,seed=100+RULES.index(name)))
        del d;gc.collect()
    allrows=one_position_per_rule(allrows)
    out={"protocol":"RULES.md originally frozen before execution; cross-symbol overlap correction after first holdout inspection; CFD adaptation of published rules", "coverage":coverage,
         "rules":{},"diagnostics":{}}
    for name in RULES:
        mainrows=[r for r in allrows if r["rule"]==name and not r["placebo"]]
        out["rules"][name]={}
        for period,cut in (("full",START),("holdout",HOLD),("recent",RECENT)):
            rr=[r for r in mainrows if cut<=pd.Timestamp(r["entry"])<END]
            v=summary(rr)
            for p in ("p_positive","p_vs_random"):
                v[p+"_bonferroni_8"]=min(1,8*v[p]) if v[p] is not None else None
            out["rules"][name][period]=v
        out["rules"][name]["by_symbol_holdout"]={sym:summary([r for r in mainrows if r["symbol"]==sym and HOLD<=pd.Timestamp(r["entry"])<END]) for sym in SYMBOLS if any(r["symbol"]==sym for r in mainrows)}
    for name in ("R7_round_cross","R8_round_fade"):
        out["diagnostics"][name+"_placebo"]={p:summary([r for r in allrows if r["rule"]==name and r["placebo"] and cut<=pd.Timestamp(r["entry"])<END]) for p,cut in (("full",START),("holdout",HOLD),("recent",RECENT))}
    for name in ("R2_sr_retest","R3_orb","R4_orb_rvol"):
        rr=[r for r in allrows if r["rule"]==name and not r["placebo"] and HOLD<=pd.Timestamp(r["entry"])<END]
        out["diagnostics"][name+"_flow_confirm"]={
            "unfiltered":summary(rr),
            "quote_direction_only":summary([r for r in rr if r["flow"]>0]),
            "tick_count_only":summary([r for r in rr if r["activity"]>=1]),
            "both":summary([r for r in rr if r["flow"]>0 and r["activity"]>=1])}
    for name in ("R7_round_cross","R8_round_fade"):
        for mode in ("round","placebo"):
            moves=np.concatenate([round_moves[f"{name}_{sym}_{mode}"] for sym in ("EURUSD","GBPUSD","USDJPY")])
            out["diagnostics"][f"{name}_{mode}_15min_price"]={
                "events":len(moves),"mean_grid_units":float(moves.mean()),
                "fraction_in_rule_direction":float(np.mean(moves>0))}
    with open(ROOT/"results.json","w",encoding="utf-8") as f:
        json.dump(out,f,indent=2,allow_nan=False)
    pd.DataFrame(allrows).to_csv(ROOT/"trades.csv",index=False)
    print("Saved",len(allrows),"trades",flush=True)


if __name__=="__main__": main()
