"""Generate the audit tables in REPORT.md from the completed frozen run."""
from pathlib import Path
import pandas as pd
import numpy as np

s=pd.read_csv('summary.csv');c=pd.read_csv('scalp_split.csv');b=pd.read_csv('seasonality.csv');f=pd.read_csv('financing.csv')
def num(x,d=3):return '—' if pd.isna(x) else f'{x:+.{d}f}'
def money(x):return '—' if pd.isna(x) else '<€0.01' if x<.01 else f'€{x:,.2f}'
def pct(x):return '—' if pd.isna(x) else f'{100*x:.1f}%'
def line(r,window=True,control=True):
    vals=[str(r.rule),str(r.symbol)]
    if window:vals.append(str(r.window))
    vals += [str(int(r.n)),num(r['mean'],4),num(r.t,2),pct(r.win),money(r.final),pct(r.dd)]
    if control:vals += [num(r.random_mean,4),num(r.paired_t,2),f'{r.bonf_random:.3g}']
    return '| '+' | '.join(vals)+' |'
def table(df,control=True):
    head='| Rule | Symbol | Window | Trades | Avg R | t | Wins | €1,000 → | Max DD |'
    sep='|---|---|---|---:|---:|---:|---:|---:|---:|'
    if control:head+=' Random R | Paired t | Bonf p |';sep+='---:|---:|---:|'
    return '\n'.join([head,sep]+[line(r,control=control) for _,r in df.iterrows()])

arules=['NR4','NR7','Inside','Williams','TurtleSoup','Donchian20','Donchian55','MA50_200','Pullback','LondonAsian']
mlrules=['ML_1h','ML_24h']
brules=['SeasonHour','SeasonWeekday']
apool=s[(s.rule.isin(arules))&(s.symbol=='ALL')&(s.window.isin(['full','holdout','recent']))].copy()
apool.rule=pd.Categorical(apool.rule,arules,ordered=True)
apool.window=pd.Categorical(apool.window,['full','holdout','recent'],ordered=True)
apool=apool.sort_values(['rule','window'])
cpool=c[(c.symbol=='ALL')].copy().sort_values(['rule','window'])
mpool=s[(s.rule.isin(mlrules))&(s.symbol=='ALL')].copy().sort_values(['rule','window'])
bpool=s[(s.rule.isin(brules))&(s.symbol=='ALL')].copy().sort_values(['rule','window'])
detail=s[(s.symbol!='ALL')&(s.window.isin(['full','recent']))].copy().sort_values(['rule','symbol','window'])

text=['# Technical edge hunt on Exness Standard bid/ask bars','',
      'Research completed 20 October 2026. [Frozen rules](RULES.md) · [Executable code](research.py) · [Raw results](results.json) · [Summary CSV](summary.csv) · [Seasonality cells](seasonality.csv) · [Scalp split](scalp_split.csv).','',
      '## Direct answer','',
      'VERDICT_PLACEHOLDER','',
      '## Execution and inference','',
      'Signals and execution follow RULES.md. Buy at observed ask, sell at observed bid, enter next M1/hour/day open after the signal, check adverse stop first, and size each separate rule account to 2% initial-stop risk. Balances start at €1,000 independently in every reported window. The full window begins 2016-10-01 for FX/gold and 2019-08-01 for indices, subject to required lookback and available data. Recent is 2024-10-01..2026-09-30. The holdout for A/B/D is 2022-01-01..2026-09-30; C uses 2025-10-01..2026-09-30. A zero-swap assumption applies to overnight daily strategies, with a sensitivity in E. The Bonferroni p column tests rule R minus seeded same-entry random-direction R and includes all candidate rule-symbol tests and all B discovery cells. Trade t tests ignore dependence, so even small nominal p values need caution.','',
      '## A. Classic technical setups','',
      'Each row is a pooled rule account across its allowed symbols, ordered by entry time. The breakout adaptations, UTC day boundary, and exits are specified in RULES.md.','',table(apool),'',
      'A_VERDICT_PLACEHOLDER','',
      '## B. UTC hour and weekday seasonality','',
      f'The design scan contained {len(b[b.window=="design"])} instrument-hour/weekday cells. Benjamini-Hochberg q=0.05 was applied across the entire design scan before the holdout. The complete net-after-spread map, including unselected cells, is in [seasonality.csv](seasonality.csv).','']
sel=b[(b.window=='design')&(b.selected==True)]
if len(sel):
    text += ['Selected design cells:','', '| Symbol | Type | UTC cell | Direction | Design n | Design mean R | Design t |','|---|---|---:|---|---:|---:|---:|']
    for _,r in sel.iterrows(): text.append(f'| {r.symbol} | {r.type} | {int(r.cell)} | {"long" if r.direction==1 else "short"} | {int(r.n)} | {num(r["mean"],4)} | {num(r.t,2)} |')
    text += ['',table(bpool),'']
else:text += ['No hour or weekday cell passed the design FDR screen; no B trade was placed in the holdout.','']
text += ['B_VERDICT_PLACEHOLDER','',
         '## C. One to fifteen minute scalps at low-era spread plus slippage','',
         'Each named variant is fixed across four symbols. Full and recent are the same 2024-10..2026-09 low-spread interval for C. The table separates design (2024-10..2025-09) from the single untouched test (2025-10..2026-09). The complete per-symbol full/recent figures are in the appendix.','',table(cpool),'',
         'C_VERDICT_PLACEHOLDER','',
         '## D. Walk-forward gradient boosting','',
         'A new HistGradientBoosting model was fit at each calendar-year boundary using prior years only. The 0.55/0.45 probability threshold, features and risk rules were frozen before the run; yearly fit and signal counts are in results.json.','',table(mpool),'',
         'D_VERDICT_PLACEHOLDER','',
         '## E. Overnight financing and swap-free eligibility','',
         'Exness says swap-free status is shared across account types, including Standard -m, and currently lists EURUSD, GBPUSD, USDJPY, XAUUSD, and all indices as eligible instruments. Its help page says accounts are swap-free by default but qualification depends on trading activity; persistent large overnight positions can cause status loss. Status must be checked in the Personal Area. [Swap-free status](https://get.exness.help/hc/en-us/articles/4402341895570-Swap-free-status), [Standard account](https://get.exness.help/hc/en-us/articles/17537782738460-Standard-account), [account suffixes](https://get.exness.help/hc/en-us/articles/360014560220-Account-type-suffixes).','',
         'Where swap applies, Exness describes daily charges or credits, Wednesday triple swap for FX/metals, Friday triple swap for indices, and rates that can change. Historical account-specific rates are unavailable in this data. [Exness swap schedule and formula](https://get.exness.help/hc/en-us/articles/360014709151-About-swap), [client agreement](https://www.exness.com/cdn/media/exnesssc/exness_sc_client_agreement.pdf).','',
         'The A trend rows above are the requested zero-swap rerun: identical price executions and zero financing. The following sensitivity subtracts an assumed 0.01% of notional per calendar day from Donchian and MA trend trades; this is **not** a quoted Exness rate.','',
         '| Rule | Window | Trades | Avg R after debit | t | Wins | €1,000 → | Max DD |','|---|---|---:|---:|---:|---:|---:|---:|']
for _,r in f.iterrows():text.append(f'| {r.rule} | {r.window} | {int(r.n)} | {num(r["mean"],4)} | {num(r.t,2)} | {pct(r.win)} | {money(r.final)} | {pct(r.dd)} |')
text += ['', 'E_VERDICT_PLACEHOLDER','',
         '## Limits and forward test','',
         'LIMITS_PLACEHOLDER','',
         'FORWARD_PLACEHOLDER','',
         '## Appendix: every symbol-rule full and recent result','',
         'For C, both windows represent the low-spread era and are identical; its actual design/test split is in section C and scalp_split.csv. All R figures include observed spread, and C also includes stipulated extra slippage.','',
         table(detail)]
Path('REPORT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
print('WROTE REPORT.md',len(text),'lines',len(detail),'detail rows')
