"""Rebuild B cell diagnostics in frozen design direction; preserve A/C/D trades."""
import gc,json
import research as r

data=json.load(open('results.json',encoding='utf-8'))
assert not any(t['rule'].startswith('Season') for t in data['trades'])
r.TRADES.extend(data['trades'])
for sym in r.SYMS:
    print('B MAP',sym,flush=True)
    m=r.read_symbol(sym)
    r.seasonality(sym,m)
    del m;gc.collect()
assert len(r.TRADES)==len(data['trades'])
r.summarize()
print('REBUILT',len(r.TRADES),len(r.MAP),flush=True)
