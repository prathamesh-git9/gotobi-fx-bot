"""The keepers plus the overnight NASDAQ hold (zero swap), as daily-compounded sleeves, Sep 2019 - Sep 2026.
Sleeves as in strategies/edge7/lab7.py P (gotobi 6%, EURJPY gotobi long 3%, GBPUSD month-end 3%, NASDAQ noise-area
momentum half size at today's spread) + overnight NASDAQ at 1x notional (strategies/trend/overnight.py, real spread).

  python strategies/trend/portfolio5.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "edge7"))
sys.path.insert(0, str(ROOT / "strategies" / "breakouts"))
sys.path.insert(0, str(HERE))
import lab7  # noqa: E402
import overnight  # noqa: E402
import lab6  # noqa: E402
import lab6_today_cost  # noqa: E402,F401

s = {"gotobi USDJPY 6%": lab7.sleeve_gotobi() * 0.06, "EURJPY long 3%": lab7.sleeve_eurjpy() * 0.03,
     "GBP month-end 3%": lab7.sleeve_gbp_fix() * 0.03, "NASDAQ momentum x0.5": lab6.b2_daily("USTECm")[0] * 0.5,
     "NASDAQ overnight 1x": overnight.run("USTECm").on}
idx = pd.bdate_range("2019-09-02", "2026-09-30")
df = pd.DataFrame({k: v.groupby(v.index.normalize()).sum().reindex(idx).fillna(0.0) for k, v in s.items()})
print(df.corr().round(2).to_string())
four = df.drop(columns=["NASDAQ overnight 1x"]).sum(axis=1)
five = df.sum(axis=1)
base = df["gotobi USDJPY 6%"]
k4 = base[base.index < "2022"].std() / four[four.index < "2022"].std()
k5 = base[base.index < "2022"].std() / five[five.index < "2022"].std()
for name, x in (("gotobi alone", base), (f"four keepers x{k4:.2f}", four * k4), (f"four + overnight x{k5:.2f}", five * k5)):
    for wn, a, b in (("since Sep 2019", "2019-09-02", "2026-10-01"), ("last 2 yrs", "2024-10-01", "2026-10-01"), ("2026", "2026-01-01", "2026-10-01")):
        st = lab7.stats(x, a, b)
        print(f"  {name:26} {wn:15}: EUR 1,000 -> {st['eur']:>7,} ({st['cagr']:+5.1f}%/yr, max drop {st['dd']:4.1f}%, Sharpe {st['sharpe']:.2f})")
