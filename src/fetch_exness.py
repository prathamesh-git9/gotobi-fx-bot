"""Build 1-minute bid/ask OHLC bars from Exness's public tick archive.

Source: https://ticks.ex2archive.com/ticks/{SYM}/{YYYY}/{MM}/Exness_{SYM}_{YYYY}_{MM}.zip
The 'm' suffix symbols are the Standard (commission-free) account feed, so the spread
in these files is the full trading cost a retail Standard account pays.
"""
import io
import sys
import zipfile
from pathlib import Path

import pandas as pd
import requests

URL = "https://ticks.ex2archive.com/ticks/{s}/{y}/{m:02d}/Exness_{s}_{y}_{m:02d}.zip"
DATA = Path(__file__).resolve().parent.parent / "data"


def month_bars(sym, y, m):
    r = requests.get(URL.format(s=sym, y=y, m=m), headers={"User-Agent": "Mozilla/5.0"}, timeout=600)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z, z.open(z.namelist()[0]) as f:
        t = pd.read_csv(f, usecols=["Timestamp", "Bid", "Ask"])
    t.index = pd.to_datetime(t.pop("Timestamp"), utc=True).dt.tz_localize(None)
    # order-flow proxy (tick rule): a tick whose mid rises counts as a buy, one that falls as a sell
    mid = (t["Bid"] + t["Ask"]) / 2
    step = mid.diff()
    t["up"] = (step > 0).astype("int32")
    t["dn"] = (step < 0).astype("int32")
    g = t.resample("1min")
    bid = g["Bid"].ohlc().add_prefix("b")
    ask = g["Ask"].ohlc().add_prefix("a")
    bars = pd.concat([bid, ask, g["Bid"].count().rename("n"), g["up"].sum(), g["dn"].sum()], axis=1)
    return bars[bars["n"] > 0]


def main(sym, y0, y1, m1_last, tag=""):
    out = DATA / f"{sym}{tag}_m1.parquet"   # same bars plus up/dn tick-flow columns
    parts = []
    for y in range(y0, y1 + 1):
        for m in range(1, 13):
            if y == y1 and m > m1_last:
                break
            b = month_bars(sym, y, m)
            if b is not None:
                parts.append(b)
                print(sym, y, m, len(b), flush=True)
    pd.concat(parts).sort_index().to_parquet(out)
    print("saved", out)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), *sys.argv[5:6])
