"""EUR 1,000 from 1 Jan 2026 to the latest data: the strategies that work, including the two scalps.
  python strategies/scalping/ytd_2026.py"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "edge7"))
sys.path.insert(0, str(ROOT / "strategies" / "breakouts"))
import lab7  # noqa: E402

START = "2026-01-01"


def grow(r, risk):
    eq = 1000 * np.cumprod(1 + risk * np.asarray(r, float))
    peak = np.maximum.accumulate(np.r_[1000, eq])
    return eq[-1], (1 - np.r_[1000, eq] / peak).max()


t = pd.read_csv(ROOT / "strategies" / "edge7" / "gotobi_bot_trades_2016_2026.csv")
t["c"] = pd.to_datetime(t.closed, utc=True).dt.tz_convert(None)
t = t[t.c >= START].sort_values("c")
print(f"gotobi trades {t.c.min():%d %b} .. {t.c.max():%d %b %Y}")
for name, sub in (("gotobi bot (long + Tokyo-fix short)", t), ("Tokyo-fix SHORT scalp only (30 min)", t[t.trade == "short"]),
                  ("gotobi long only", t[t.trade == "long"])):
    for risk in (0.06, 0.10):
        e, dd = grow(sub.r, risk)
        print(f"  {name:38} {risk:.0%}: {len(sub):3} trades -> EUR {e:,.0f} ({e / 1000 - 1:+.0%}), max drop {dd:.0%}")
gbp = lab7.sleeve_gbp_fix()
g = gbp[gbp.index >= START]
for risk in (0.03, 0.06):
    e, dd = grow(g.values, risk)
    print(f"  GBPUSD month-end 15-min SCALP           {risk:.0%}: {len(g):3} trades -> EUR {e:,.0f} ({e / 1000 - 1:+.0%}), max drop {dd:.0%}"
          f"   [{', '.join(f'{d:%b} {r * 25:+.1f}p' for d, r in g.items())}]")
import lab6  # noqa: E402
import lab6_today_cost  # noqa: E402,F401  (2026 spreads are already today's)
nq = lab6.b2_daily("USTECm")[0]
x = nq[nq.index >= START]
eq = 1000 * (1 + x).cumprod()
print(f"  NASDAQ noise-area momentum (paper sizing): {(x != 0).sum()} trading days to {x.index.max():%d %b} -> EUR {eq.iloc[-1]:,.0f}"
      f" ({eq.iloc[-1] / 1000 - 1:+.0%}), max drop {(1 - eq / eq.cummax()).max():.0%}")
