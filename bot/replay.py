"""Run the real bot (engine + broker wrapper + journal) on the MT5 simulator over historical Exness data.

  python -m bot.replay --start 2026-01-01 --end 2026-10-16 --balance 1000 --risk 10

This is an end-to-end backtest of the production code, and the harness for tests/test_replay.py.
The bot is stepped every minute around each trade window and every 15 minutes otherwise; prices and stops are
simulated minute by minute in between.
"""
from __future__ import annotations

import argparse
import logging
import tempfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from .broker import MT5Broker
from .config import Config
from .engine import Engine
from .fake_mt5 import FakeMT5
from .gotobi_calendar import GotobiCalendar
from .journal import Journal

DATA = Path(__file__).resolve().parent.parent / "data"
UTC = timezone.utc
BAR_COLS = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]


def load_bars(symbol: str = "USDJPYm") -> pd.DataFrame:
    files = [f"{symbol}_2016_m1.parquet", f"{symbol}_m1.parquet", f"{symbol}_2026_10_m1.parquet"]
    df = pd.concat([pd.read_parquet(DATA / f, columns=BAR_COLS) for f in files if (DATA / f).exists()]).sort_index()
    return df[~df.index.duplicated()]


def load_eurusd() -> pd.Series:
    """EUR/USD for converting profits: Exness minute mids from 2019, Yahoo daily closes before that."""
    parts = []
    y = pd.read_parquet(DATA / "daily_yahoo.parquet", columns=["date", "sym", "close"])
    y = y[y.sym == "EURUSD=X"]
    daily = pd.Series(y.close.to_numpy(), index=pd.to_datetime(y.date).dt.tz_localize(None)).sort_index()
    parts.append(daily[daily.index < "2019-01-01"])
    for f in ("EURUSDm_m1.parquet", "EURUSDm_2026_10_m1.parquet"):
        if (DATA / f).exists():
            m = pd.read_parquet(DATA / f, columns=["bopen", "aopen"])
            parts.append((m.bopen + m.aopen) / 2)
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated()]


def step_times(cal: GotobiCalendar, start: datetime, end: datetime, coarse_min: int = 15,
               pad_min: int = 10) -> list[datetime]:
    pts = set()
    t = start
    while t <= end:
        pts.add(t)
        t += timedelta(minutes=coarse_min)
    pad = timedelta(minutes=pad_min)
    for d in cal.trade_days((start - timedelta(days=2)).date(), (end + timedelta(days=2)).date()):
        s = cal.slot(d)
        t = max(start, s.entry - pad).replace(second=0, microsecond=0)
        stop = min(end, max(s.exit, s.fix) + pad)
        while t <= stop:
            pts.add(t)
            t += timedelta(minutes=1)
    return sorted(pts)


def replay(cfg: Config, fake: FakeMT5, start: datetime, end: datetime, state_dir: str | Path,
           restart_at: set[int] = frozenset(), down: list[tuple[datetime, datetime]] = ()) -> tuple[Journal, Engine]:
    """Step the bot through [start, end]. restart_at: step numbers at which the bot is killed and restarted from
    its saved state; down: windows in which the bot is not running at all (the market keeps moving)."""
    cal = GotobiCalendar.from_config(cfg)
    times = step_times(cal, start, end)
    fake.set_time(times[0])
    journal = Journal(state_dir, durable=False)
    engine = Engine(cfg, MT5Broker(fake), journal)
    engine.startup(times[0])
    for i, now in enumerate(times):
        if any(a <= now < b for a, b in down):
            continue
        fake.set_time(now)
        if i in restart_at:
            journal = Journal(state_dir, durable=False)
            engine = Engine(cfg, MT5Broker(fake), journal)
            engine.startup(now)
        engine.step(now)
    return journal, engine


def trades_frame(journal: Journal) -> pd.DataFrame:
    rows = []
    for key, rec in journal.closed():
        rows.append({"gotobi": key, "opened": rec.get("opened"), "closed": rec.get("closed"),
                     "entry": rec.get("entry_price"), "exit": rec.get("close_price"), "lots": rec.get("volume"),
                     "pips": round((rec["close_price"] - rec["entry_price"]) * 100, 2) if rec.get("close_price") else None,
                     "pnl": rec.get("pnl"), "r": rec.get("r"), "reason": rec.get("reason")})
    return pd.DataFrame(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay the Gotobi bot on historical Exness data")
    ap.add_argument("--start", default="2026-01-01")
    ap.add_argument("--end", default="2026-10-16")
    ap.add_argument("--balance", type=float, default=1000.0)
    ap.add_argument("--risk", type=float, default=Config().risk_pct)
    ap.add_argument("--leverage", type=int, default=30)
    ap.add_argument("--out", help="write the trade list to this CSV")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = (datetime.fromisoformat(args.end) + timedelta(hours=23, minutes=59)).replace(tzinfo=UTC)
    bars = load_bars()
    bars = bars[(bars.index >= start.replace(tzinfo=None) - timedelta(days=3)) &
                (bars.index <= end.replace(tzinfo=None) + timedelta(days=1))]
    fake = FakeMT5(bars, load_eurusd(), balance=args.balance, leverage=args.leverage)
    cfg = replace(Config(), risk_pct=args.risk)
    with tempfile.TemporaryDirectory() as tmp:
        journal, _ = replay(cfg, fake, start, end, tmp)
        t = trades_frame(journal)
        others = {k: v for k, v in journal.slots.items() if v.get("status") != "closed"}
    if args.out:
        t.to_csv(args.out, index=False)
    print(t.to_string(index=False))
    won = (t.pnl > 0).sum()
    print(f"\n{len(t)} trades, {won} won ({won / max(len(t), 1):.0%}); balance {args.balance:,.2f} -> {fake.balance:,.2f} "
          f"({fake.balance / args.balance - 1:+.1%}); stops {int((t.reason == 'stop').sum())}")
    for k, v in sorted(others.items()):
        print(f"  {k}: {v.get('status')} - {v.get('note')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
