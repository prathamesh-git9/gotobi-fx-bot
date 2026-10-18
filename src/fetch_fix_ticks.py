"""Keep the raw Exness USDJPYm ticks around the 09:55 JST Tokyo fix (00:45-01:35 UTC, every day 2016-2026).

Minute bars cannot say whether the post-fix drop is catchable by a bot: it might all happen in the first
seconds after 09:55:00. These ticks answer that (src/fix_seconds.py).
Output: data/fix_ticks/USDJPYm_YYYY_MM.parquet (bid, ask; index = UTC tick time). Resumable.
"""
import io
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import requests

URL = "https://ticks.ex2archive.com/ticks/{s}/{y}/{m:02d}/Exness_{s}_{y}_{m:02d}.zip"
OUT = Path(__file__).resolve().parent.parent / "data" / "fix_ticks"
SYM = "USDJPYm"


def month(ym):
    y, m = ym
    f = OUT / f"{SYM}_{y}_{m:02d}.parquet"
    if f.exists():
        return f"{y}-{m:02d} cached"
    r = requests.get(URL.format(s=SYM, y=y, m=m), headers={"User-Agent": "Mozilla/5.0"}, timeout=900)
    if r.status_code == 404:
        return f"{y}-{m:02d} missing"
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as z, z.open(z.namelist()[0]) as fh:
        t = pd.read_csv(fh, usecols=["Timestamp", "Bid", "Ask"])
    t.index = pd.to_datetime(t.pop("Timestamp"), utc=True).dt.tz_localize(None)
    tod = t.index.hour * 60 + t.index.minute
    t = t[(tod >= 45) & (tod < 95)].rename(columns={"Bid": "bid", "Ask": "ask"})
    tmp = f.with_suffix(".tmp")
    t.to_parquet(tmp)
    tmp.replace(f)
    return f"{y}-{m:02d} {len(t)} ticks"


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    months = [(y, m) for y in range(2016, 2027) for m in range(1, 13) if (y, m) <= (2026, 10)]
    with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 3) as ex:
        for msg in ex.map(month, months):
            print(msg, flush=True)
    print("done")
