"""B1 and B2 again with NO spread (bid = ask = mid): separates "the signal is absent" from "the spread eats it".
  python strategies/breakouts/lab6_gross.py"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab6  # noqa: E402

_load = lab6.load


def mid_load(sym, flow=False):
    df = _load(sym, flow)
    for x in ("open", "high", "low", "close"):
        m = (df["b" + x] + df["a" + x]) / 2
        df["b" + x] = m
        df["a" + x] = m
    return df


lab6.load = mid_load
for k in sys.argv[1:] or ["B1", "B2"]:
    print(f"\n===== {k} gross (no spread) =====")
    getattr(lab6, k)()
