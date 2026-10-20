"""B2 (and B1) with TODAY's Exness spread applied to the whole history: bid/ask = mid -+ half of the median cash-session
spread of Oct 2024 - Sep 2026 (US500 0.95 bp, USTEC 0.85 bp, US30 and DE30 left at their real spreads).
  python strategies/breakouts/lab6_today_cost.py [B2 B1]"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab6  # noqa: E402

BP = {"US500m": 0.95e-4, "USTECm": 0.85e-4}
_load = lab6.load


def today_load(sym, flow=False):
    df = _load(sym, flow)
    if sym in BP:
        for x in ("open", "high", "low", "close"):
            m = (df["b" + x] + df["a" + x]) / 2
            df["b" + x] = m * (1 - BP[sym] / 2)
            df["a" + x] = m * (1 + BP[sym] / 2)
    return df


lab6.load = today_load

if __name__ == "__main__":
    for k in sys.argv[1:] or ["B2"]:
        print(f"\n===== {k} at today's spread =====")
        getattr(lab6, k)()
