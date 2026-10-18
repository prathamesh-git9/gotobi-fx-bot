"""EUR 1,000 compounded with the real bot (sizing, stops, take-profit, short, kill switch, 0.2 bp slippage), one
continuous account, 1:30 leverage, EUR account (USD/JPY profits converted at the day's EUR/USD).

  python src/gotobi_compound.py old          2006-2015, HistData bid + Exness 2016-18 spread profile
  python src/gotobi_compound.py old-stress   the same with every spread 1 pip wider
  python src/gotobi_compound.py old-nokill   2006-2015 with the kill switch switched off
  python src/gotobi_compound.py ytd          1 Jan 2026 - 16 Oct 2026, real Exness bid/ask
"""
import logging
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bot.config import Config  # noqa: E402
from bot.fake_mt5 import FakeMT5  # noqa: E402
from bot.replay import load_bars, load_eurusd, replay, trades_frame  # noqa: E402
from src.gotobi_20y import ASK, BID, HD, exness, spread_profile, synth  # noqa: E402

UTC = timezone.utc


def main(which: str) -> None:
    logging.disable(logging.CRITICAL)
    if which.startswith("old"):
        ex = exness()
        bars = synth(pd.read_parquet(HD), spread_profile(ex), extra_pips=1.0 if which == "old-stress" else 0.0)
        t0, t1 = datetime(2006, 1, 4, tzinfo=UTC), datetime(2015, 12, 31, 23, 59, tzinfo=UTC)
    else:
        bars = load_bars()[BID + ASK]
        t0, t1 = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 10, 16, 23, 59, tzinfo=UTC)
    bars = bars[(bars.index >= pd.Timestamp(t0.replace(tzinfo=None)) - pd.Timedelta(days=4)) &
                (bars.index <= pd.Timestamp(t1.replace(tzinfo=None)) + pd.Timedelta(days=1))]
    fake = FakeMT5(bars, load_eurusd(), balance=1000.0, currency="EUR", leverage=30)
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=6.0)
    if which.endswith("nokill"):
        cfg = replace(cfg, kill_sum_r=-1e9, kill_max_drawdown=0.99)
    with tempfile.TemporaryDirectory() as tmp:
        journal, _ = replay(cfg, fake, t0, t1, tmp)
        t = trades_frame(journal)
        halted = journal.halted
        notes = [(k, v.get("status"), v.get("note")) for k, v in sorted(journal.slots.items())
                 if v.get("status") != "closed"]
    out = ROOT / "results" / f"gotobi_compound_{which}.csv"
    t.to_csv(out, index=False)
    bal = 1000.0 + t.pnl.cumsum()
    t["balance"] = bal
    t["year"] = t.closed.str[:4]
    peak = bal.cummax().clip(lower=1000.0)
    print(f"== {which}: {t0:%Y-%m-%d} to {t1:%Y-%m-%d}, EUR 1,000 at 6% risk, compounded")
    start = 1000.0
    for y, g in t.groupby("year"):
        end = g.balance.iloc[-1]
        yb = pd.concat([pd.Series([start]), g.balance])
        ydd = (1 - yb / yb.cummax()).max()
        print(f"  {y}: {start:10,.2f} -> {end:10,.2f}  {end / start - 1:+7.1%}  trades {len(g):3}  "
              f"pips {g.pips.sum():+7.1f}  worst drop in year {ydd:.1%}")
        start = end
    print(f"  FINAL: EUR 1,000 -> EUR {fake.balance:,.2f} ({fake.balance / 1000 - 1:+.1%}); {len(t)} trades, "
          f"{(t.pnl > 0).mean():.0%} won, max drawdown {(1 - bal / peak).max():.1%}, kill switch "
          f"{'TRIPPED: ' + str(halted) if halted else 'never tripped'}")
    skipped = [n for n in notes if n[1] != "open"]
    print(f"  not traded: {len(skipped)}" + "".join(f"\n    {k}: {s} - {n}" for k, s, n in skipped[:15]))


if __name__ == "__main__":
    main(sys.argv[1])
