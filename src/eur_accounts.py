"""The production bot (long + 30-pip take-profit + post-fix short, 6% risk) on EUR accounts, replayed on real
Exness history with the bot's own code: EUR 1,000 from 1 Jan 2026, and EUR 100 from 1 Jan 2025.

EUR accounts: every profit is converted from USD to EUR at that moment's EUR/USD (Exness minute data).
EUR 100 on a Standard account: the minimum trade is 0.01 lot (1,000 USD), worth about EUR 3.1 of risk at a 55-pip
stop, so the size cannot follow 6% exactly (0.01 lot until about EUR 104, then 0.02, ...); a Cent account
(same USD/JPY prices, 100x smaller units) can, and is shown too. The kill switch stays on.
"""
import logging
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from bot.config import Config  # noqa: E402
from bot.fake_mt5 import FakeMT5  # noqa: E402
from bot.replay import load_bars, load_eurusd, replay, trades_frame  # noqa: E402

UTC = timezone.utc
END = datetime(2026, 10, 16, 23, 59, tzinfo=UTC)
RES = ROOT / "results"


OLD = {"take_profit_pips": 0.0, "post_fix_short": False}     # the plain long, for comparison


def run(balance: float, start: str, contract: float, tag: str, risk: float = 6.0, leverage: int = 500,
        end: str | None = None, **overrides):
    logging.disable(logging.CRITICAL)
    bars, eu = load_bars(), load_eurusd()
    t0 = datetime.fromisoformat(start).replace(tzinfo=UTC)
    t1 = datetime.fromisoformat(end).replace(hour=23, minute=59, tzinfo=UTC) if end else END
    bars = bars[(bars.index >= t0.replace(tzinfo=None) - timedelta(days=3))]
    fake = FakeMT5(bars, eu, balance=balance, currency="EUR", leverage=leverage, contract=contract)
    cfg = replace(Config(), symbols=("USDJPYm",), risk_pct=risk, **overrides)
    with tempfile.TemporaryDirectory() as tmp:
        journal, _ = replay(cfg, fake, t0, t1, tmp)
        t = trades_frame(journal)
        others = {k: v for k, v in journal.slots.items() if v.get("status") != "closed"}
        halted = journal.halted
    t.to_csv(RES / f"bot_v2_{tag}.csv", index=False)
    bal = balance + t.pnl.cumsum()
    peak = bal.cummax().clip(lower=balance)
    dd = float((1 - bal / peak).max())
    lng, sh = t[t.trade == "long"], t[t.trade == "short"]
    skipped = sum(1 for v in others.values() if v.get("status") in ("skipped", "missed"))
    print(f"{tag}: EUR {balance:,.0f} from {start} -> EUR {fake.balance:,.2f} ({fake.balance / balance - 1:+.1%}); "
          f"max drawdown {dd:.0%}; {len(t)} trades ({len(lng)} long, {len(sh)} short), won {(t.pnl > 0).mean():.0%}; "
          f"long EUR {lng.pnl.sum():+,.2f}, short EUR {sh.pnl.sum():+,.2f}; lots {t.lots.min()}-{t.lots.max()}; "
          f"not traded {skipped}{'; KILL SWITCH ' + str(halted) if halted else ''}")
    return t


if __name__ == "__main__":
    run(1000.0, "2026-01-01", 100_000.0, "eur1000_2026_6pct")
    run(100.0, "2025-01-01", 100_000.0, "eur100_2025_2026_6pct_standard")
    run(100.0, "2025-01-01", 1_000.0, "eur100_2025_2026_6pct_cent")     # Cent: 100x smaller units
    run(100.0, "2026-01-01", 100_000.0, "eur100_2026_6pct_standard")
    run(100.0, "2026-01-01", 1_000.0, "eur100_2026_6pct_cent")
    run(100.0, "2026-01-01", 100_000.0, "eur100_2026_6pct_standard_old", **OLD)
    run(100.0, "2026-01-01", 1_000.0, "eur100_2026_6pct_cent_old", **OLD)
