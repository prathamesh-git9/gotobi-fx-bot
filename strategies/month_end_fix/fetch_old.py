"""EURUSD and GBPUSD 1-minute BID bars 2006-2015 from HistData.com (same source and time-zone handling as the
gotobi bot's src/fetch_histdata.py, which is left untouched). Timestamps are New York local time with daylight
saving. Saved to strategies/month_end_fix/data/{PAIR}_hd_bid_m1.parquet (naive UTC index, bopen/bhigh/blow/bclose).

  python strategies/month_end_fix/fetch_old.py
"""
import io
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
OUT = HERE / "data"
PAGE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/{p}/{y}"


def fetch(s, pair, y):
    dest = OUT / "raw" / f"{pair}_{y}.zip"
    if dest.exists() and dest.stat().st_size > 100_000:
        return dest
    page = PAGE.format(p=pair.lower(), y=y)
    r = s.get(page, timeout=60)
    r.raise_for_status()
    m = re.search(r'id="tk"[^>]*value="([^"]+)"', r.text) or re.search(r'value="([^"]+)"[^>]*id="tk"', r.text)
    data = {"tk": m.group(1), "date": str(y), "datemonth": str(y), "platform": "ASCII", "timeframe": "M1", "fxpair": pair}
    r = s.post("https://www.histdata.com/get.php", data=data, timeout=300,
               headers={"Referer": page, "Origin": "https://www.histdata.com"})
    r.raise_for_status()
    assert r.content.startswith(b"PK"), f"{pair} {y}: not a zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    time.sleep(3)
    return dest


def parse(path):
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(io.BytesIO(z.read(name)), sep=";", header=None, names=["t", "bopen", "bhigh", "blow", "bclose", "vol"])
    local = pd.DatetimeIndex(pd.to_datetime(df.t, format="%Y%m%d %H%M%S"))
    t = local.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").tz_convert("UTC").tz_localize(None)
    out = df.drop(columns=["t", "vol"]).set_index(pd.DatetimeIndex(t, name="Timestamp"))
    return out[out.index.notna()]


def main():
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    for pair in ("EURUSD", "GBPUSD"):
        parts = [parse(fetch(s, pair, y)) for y in range(2006, 2016)]
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated()]
        df.to_parquet(OUT / f"{pair}_hd_bid_m1.parquet")
        print(pair, len(df), df.index[0], df.index[-1])


if __name__ == "__main__":
    main()
