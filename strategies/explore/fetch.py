"""Exness Standard 1-minute bid/ask bars for the new markets, saved to strategies/explore/data/{SYM}_m1.parquet.
Uses src/fetch_exness.month_bars (read only; the gotobi bot is not touched).

  python strategies/explore/fetch.py SYM FIRST_YEAR
"""
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))
from fetch_exness import month_bars  # noqa: E402

sym, y0 = sys.argv[1], int(sys.argv[2])
out = HERE / "data" / f"{sym}_m1.parquet"
parts = []
for y in range(y0, 2027):
    for m in range(1, 13):
        if (y, m) > (2026, 9):
            break
        b = month_bars(sym, y, m)
        if b is not None:
            parts.append(b.drop(columns=["up", "dn", "n"]))
pd.concat(parts).sort_index().to_parquet(out)
print("saved", sym, len(pd.read_parquet(out)))
