"""Turn the bot's switches one at a time over the last two years: the real bot (engine, sizing, stops, kill switch,
0.2 bp slippage) on Exness bid/ask, EUR 1,000 account, 1:500 leverage (so margin never caps the size).

  python src/gotobi_switches.py           -> results/gotobi_switches.csv and the trade lists
"""
import logging
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bot.config import Config  # noqa: E402
from bot.fake_mt5 import FakeMT5  # noqa: E402
from bot.replay import load_bars, load_eurusd, replay, trades_frame  # noqa: E402

UTC = timezone.utc
T0, T1 = datetime(2024, 10, 17, tzinfo=UTC), datetime(2026, 10, 16, 23, 59, tzinfo=UTC)
NOKILL = {"kill_sum_r": -1e9, "kill_max_drawdown": 0.99}
VARIANTS = {
    "base (as deployed, 6%)": {},
    "risk 2%": {"risk_pct": 2.0}, "risk 4%": {"risk_pct": 4.0}, "risk 8%": {"risk_pct": 8.0},
    "risk 10%": {"risk_pct": 10.0},
    "no take-profit": {"take_profit_pips": 0.0}, "take-profit 20": {"take_profit_pips": 20.0},
    "take-profit 50": {"take_profit_pips": 50.0},
    "stop 35": {"stop_pips": 35.0, "short_stop_pips": 35.0}, "stop 75": {"stop_pips": 75.0, "short_stop_pips": 75.0},
    "long only (no short)": {"post_fix_short": False},
    "no kill switch": NOKILL,
    "no kill switch, 10%": {**NOKILL, "risk_pct": 10.0},
    "spread limit 2 pips": {"max_spread_pips": 2.0},
}


def run(item):
    name, ov = item
    logging.disable(logging.CRITICAL)
    bars = load_bars()
    bars = bars[(bars.index >= pd.Timestamp("2024-10-12")) & (bars.index <= pd.Timestamp("2026-10-18"))]
    fake = FakeMT5(bars, load_eurusd(), balance=1000.0, currency="EUR", leverage=500)
    cfg = replace(Config(), **{"symbols": ("USDJPYm",), "risk_pct": 6.0, **ov})
    with tempfile.TemporaryDirectory() as tmp:
        journal, _ = replay(cfg, fake, T0, T1, tmp)
        t = trades_frame(journal)
        halted = journal.halted
    bal = 1000.0 + t.pnl.cumsum()
    dd = float((1 - bal / bal.cummax().clip(lower=1000.0)).max())
    month = t.assign(m=t.closed.str[:7]).groupby("m").pnl.sum()
    safe = name.split(" (")[0].replace(" ", "_").replace("%", "pct").replace(",", "")
    t.to_csv(ROOT / "results" / f"switch_{safe}.csv", index=False)
    lg, sh = t[t.trade == "long"], t[t.trade == "short"]
    return {"variant": name, "final_eur": round(fake.balance, 2), "max_dd": round(dd, 3), "trades": len(t),
            "win": round(float((t.pnl > 0).mean()), 3), "pips_per_trade": round(float(t.pips.mean()), 2),
            "long_pips": round(float(lg.pips.mean()), 2) if len(lg) else None,
            "short_pips": round(float(sh.pips.mean()), 2) if len(sh) else None,
            "worst_month_eur": round(float(month.min()), 2), "worst_month": month.idxmin(),
            "kill_switch": (halted or {}).get("at", "no")[:10] if halted else "no"}


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(run, VARIANTS.items()))
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "results" / "gotobi_switches.csv", index=False)
    pd.set_option("display.width", 220)
    print(df.to_string(index=False))
