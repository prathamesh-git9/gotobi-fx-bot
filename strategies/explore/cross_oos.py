"""EURJPY gotobi on 2006-2015, data nobody looked at: HistData bid + ask modelled from the Exness EURJPYm 2016-18
spread for each UTC minute of the day (+0.5 pip stress). USDJPY on the same years for comparison.
Long 15:55 UTC day before -> 00:54 UTC (stop 55, TP 30), short 00:55 -> 01:25; ordinary Tokyo days as control.

  python strategies/explore/cross_oos.py
"""
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lab import COLS, ROOT, UTC, GotobiCalendar, Px, judge, tp_trade  # noqa: E402

import holidays  # noqa: E402


class Bars(Px):
    def __init__(self, df, pip):
        self.pip = pip
        self.t = df.index.values.astype("datetime64[m]").astype(np.int64)
        for c in COLS:
            setattr(self, c, df[c].to_numpy())


def eurjpy(extra):
    bid = pd.read_parquet(ROOT / "strategies/month_end_fix/data/EURJPY_hd_bid_m1.parquet")
    ex = pd.read_parquet(HERE / "data/EURJPYm_m1.parquet", columns=COLS)
    ex = ex[ex.index < "2019-01-01"]
    prof = ((ex.aopen - ex.bopen) / 0.01).groupby(ex.index.hour * 60 + ex.index.minute).median()
    sp = (prof.reindex(bid.index.hour * 60 + bid.index.minute).to_numpy() + extra) * 0.01
    df = bid[["bopen", "bhigh", "blow"]].copy()
    df["aopen"], df["ahigh"], df["alow"] = df.bopen + sp, df.bhigh + sp, df.blow + sp
    return Bars(df, 0.01)


jp = holidays.Japan(years=range(2006, 2016))
days = [d.date() for d in pd.bdate_range("2006-01-05", "2015-12-31") if d.date() not in jp
        and not (d.month == 12 and d.day == 31) and not (d.month == 1 and d.day <= 3)]
got = set(GotobiCalendar().trade_days(date(2006, 1, 1), date(2015, 12, 31)))
usd = Bars(pd.read_parquet(ROOT / "data/histdata/USDJPY_hd_model_2006_2015_m1.parquet", columns=COLS), 0.01)
for name, px in (("EURJPY", eurjpy(0.0)), ("EURJPY +0.5 pip", eurjpy(0.5)), ("USDJPY", usd)):
    longs, shorts = [], []
    for d in days:
        prev = d - timedelta(days=3 if d.weekday() == 0 else 1)
        e0 = datetime.combine(prev, time(15, 55), UTC) if d.weekday() else datetime.combine(d - timedelta(days=1), time(22, 15), UTC)
        longs.append((d, tp_trade(px, e0, datetime.combine(d, time(0, 54), UTC), +1, 55, 30), d in got))
        shorts.append((d, px.trade(datetime.combine(d, time(0, 55), UTC), datetime.combine(d, time(1, 25), UTC), -1, 55), d in got))
    print(name)
    judge(f"{name} gotobi long 2006-15 (halves 2006-10 / 2011-15)", longs, split=2010)
    judge(f"{name} gotobi short 2006-15", shorts, split=2010)
