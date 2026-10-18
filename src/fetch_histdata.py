"""USD/JPY 1-minute bars before 2016 (Exness's archive starts in 2016), from HistData.com's free yearly files.

HistData M1 ASCII: "YYYYMMDD HHMMSS;open;high;low;close;volume", BID prices only. HistData says the timestamps
are EST with no daylight saving, but against Exness 2016-2018 they follow New York time WITH daylight saving
(winter: best match at UTC-5; summer: at UTC-4), so they are converted as America/New_York local time
(src/gotobi_20y.py check). Saved as data/histdata/USDJPY_hd_bid_m1.parquet with a naive-UTC minute index
and columns bopen/bhigh/blow/bclose. The ask side is not in the data: src/gotobi_20y.py adds a spread model.
Downloads are sequential with a pause (13 small files); already-downloaded years are skipped.
"""
import io
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "histdata"
RAW = OUT / "raw"
PAGE = "https://www.histdata.com/download-free-forex-historical-data/?/ascii/1-minute-bar-quotes/usdjpy/{y}"


def fetch_year(s: requests.Session, y: int) -> Path:
    dest = RAW / f"DAT_ASCII_USDJPY_M1_{y}.zip"
    if dest.exists() and dest.stat().st_size > 100_000:
        return dest
    page = PAGE.format(y=y)
    r = s.get(page, timeout=60)
    r.raise_for_status()
    m = re.search(r'id="tk"[^>]*value="([^"]+)"', r.text) or re.search(r'value="([^"]+)"[^>]*id="tk"', r.text)
    if not m:
        raise RuntimeError(f"{y}: no download token on {page}")
    data = {"tk": m.group(1), "date": str(y), "datemonth": str(y), "platform": "ASCII", "timeframe": "M1",
            "fxpair": "USDJPY"}
    r = s.post("https://www.histdata.com/get.php", data=data, timeout=300,
               headers={"Referer": page, "Origin": "https://www.histdata.com"})
    r.raise_for_status()
    if not r.content.startswith(b"PK"):
        raise RuntimeError(f"{y}: not a zip ({len(r.content)} bytes): {r.content[:200]!r}")
    RAW.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def parse(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        df = pd.read_csv(io.BytesIO(z.read(name)), sep=";", header=None,
                         names=["t", "bopen", "bhigh", "blow", "bclose", "vol"])
    local = pd.DatetimeIndex(pd.to_datetime(df.t, format="%Y%m%d %H%M%S"))
    t = local.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT").tz_convert("UTC").tz_localize(None)
    out = df.drop(columns=["t", "vol"]).set_index(pd.DatetimeIndex(t, name="Timestamp"))
    return out[out.index.notna()]       # the DST-switch hours fall on Sunday mornings, when FX is shut


def main(first: int = 2006, last: int = 2018) -> None:
    s = requests.Session()
    s.headers["User-Agent"] = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/130.0 Safari/537.36")
    parts = []
    for y in range(first, last + 1):
        p = fetch_year(s, y)
        d = parse(p)
        print(f"{y}: {len(d):,} bars, {d.index.min()} .. {d.index.max()}", flush=True)
        parts.append(d)
        time.sleep(2)
    bars = pd.concat(parts).sort_index()
    bars = bars[~bars.index.duplicated()]
    tmp = OUT / "USDJPY_hd_bid_m1.parquet.tmp"
    bars.to_parquet(tmp)
    tmp.replace(OUT / "USDJPY_hd_bid_m1.parquet")
    print(f"saved {len(bars):,} bars")


if __name__ == "__main__":
    main(*map(int, sys.argv[1:3])) if len(sys.argv) > 2 else main()
