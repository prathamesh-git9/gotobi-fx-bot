"""NASDAQ 100 (NSXUSD) and S&P 500 (SPXUSD) 1-minute BID bars from HistData.com for 2016-2019, to extend the Exness
index CFD data (Aug 2019+) to 10 years. Same download/parse code as strategies/month_end_fix/fetch_old.py (New York
local timestamps with DST -> UTC). Saved to strategies/fabio/data/{SYM}_hd_bid_m1.parquet.

  python strategies/fabio/fetch_hd_index.py [NSXUSD SPXUSD]
"""
import sys
from pathlib import Path

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "month_end_fix"))
import fetch_old  # noqa: E402

fetch_old.OUT = HERE / "data"

if __name__ == "__main__":
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    for sym in sys.argv[1:] or ("NSXUSD", "SPXUSD"):
        parts = [fetch_old.parse(fetch_old.fetch(s, sym, y)) for y in range(2016, 2020)]
        df = pd.concat(parts).sort_index()
        df = df[~df.index.duplicated()]
        df.to_parquet(HERE / "data" / f"{sym}_hd_bid_m1.parquet")
        print(sym, len(df), df.index[0], df.index[-1])
