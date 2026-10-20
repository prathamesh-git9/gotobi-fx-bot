"""Round 8: SCALPING. My half: minute-scale reactions to scheduled US news (the only kind of scalp the earlier rounds
never tested). Qwen's and Gemini's scalping ideas are tested in lab8_ai.py. Rules fixed before running.

 N1 US 08:30 ET data shock, momentum: on any weekday whose 08:30-08:32 New York range is >= 3x the median of the
    previous 20 weekdays (known at 08:32, so no look-ahead), trade in the direction of the 08:30 -> 08:32 move at
    08:32; stop just beyond the opposite end of those two minutes; out at 08:45.
 N2 The same shock, faded (the opposite direction) - the overreaction hypothesis.
 N3 US 10:00 ET data shock (ISM, confidence, sales): N1's rule moved to 10:00 -> 10:02, out at 10:15.
 N4 FOMC statement (14:00 ET, official dates): direction of 14:00 -> 14:02, enter 14:02, stop beyond the opposite end,
    out at 14:29 (before the press conference). N5: the same, faded.
 EURUSD, USDJPY, XAUUSD (2016-2026) and US500 (2019-2026). Real bid/ask, so the release-time spread is paid.

Pass: positive in both halves (to 2021 / from 2022), beats the same entries in a random direction, t > 2.8.

  python strategies/scalping/lab8.py
"""
import gc
import json
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "strategies" / "different"))
import lab4  # noqa: E402
from lab4 import M, load, report, run  # noqa: E402

NY = ZoneInfo("America/New_York")
lab4.PIP.update({"US500m": 0.1})


def shock_scalps(m, t_rel, t_sig, t_out, fade=False, dates=None, mult=3.0):
    """t_rel release time, t_sig = release + 2 min, t_out exit (NY clock times). dates: only these days (FOMC)."""
    days = [d.date() for d in pd.bdate_range("2016-01-04", "2026-09-30")]
    ranges, sigs = [], []
    for d in days:
        i0, i2 = m.i(datetime.combine(d, t_rel, NY), tol=1), m.i(datetime.combine(d, t_sig, NY), tol=1)
        j = m.i(datetime.combine(d, t_out, NY), tol=2)
        if None in (i0, i2, j) or i2 <= i0:
            ranges.append(np.nan)
            continue
        hi = ((m.ahigh[i0:i2] + m.bhigh[i0:i2]) / 2).max()
        lo = ((m.alow[i0:i2] + m.blow[i0:i2]) / 2).min()
        rng = hi - lo
        hist = [x for x in ranges[-20:] if not np.isnan(x)]
        ranges.append(rng)
        if dates is not None:
            if d not in dates:
                continue
        elif len(hist) < 10 or rng < mult * np.median(hist):
            continue
        move = (m.aopen[i2] + m.bopen[i2]) / 2 - (m.aopen[i0] + m.bopen[i0]) / 2
        if move == 0:
            continue
        side = int(np.sign(move)) * (-1 if fade else 1)
        e = m.aopen[i2] if side > 0 else m.bopen[i2]
        stop_d = (e - lo) if side > 0 else (hi - e)   # beyond the two-minute extreme on the losing side
        if stop_d <= 0:
            continue
        sigs.append((i2, j, side, stop_d, None, 0.0))
    return sigs


def main():
    fomc = pd.read_csv(ROOT / "data" / "events_calendar.csv")
    fomc = set(pd.to_datetime(fomc[fomc.event == "fomc"].date).dt.date)
    for sym in ("EURUSDm", "USDJPYm", "XAUUSDm", "US500m"):
        df = load(sym)
        m = M(df, lab4.PIP[sym])
        del df
        gc.collect()
        plan = [("N1", "08:30 data shock, momentum", (time(8, 30), time(8, 32), time(8, 45)), False, None),
                ("N2", "08:30 data shock, faded", (time(8, 30), time(8, 32), time(8, 45)), True, None),
                ("N3", "10:00 data shock, momentum", (time(10, 0), time(10, 2), time(10, 15)), False, None),
                ("N4", "FOMC statement, momentum", (time(14, 0), time(14, 2), time(14, 29)), False, fomc),
                ("N5", "FOMC statement, faded", (time(14, 0), time(14, 2), time(14, 29)), True, fomc)]
        for code, name, (a, b, c), fade, dates in plan:
            sigs = shock_scalps(m, a, b, c, fade=fade, dates=dates)
            report(f"{code} {sym[:-1]} {name}", *run(m, sigs))
        del m
        gc.collect()
    (HERE / "lab8_results.json").write_text(json.dumps(lab4.OUT, indent=1, default=str))


if __name__ == "__main__":
    main()
