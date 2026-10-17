"""Shared helpers: synthetic minute markets for the simulator, and engine/broker wiring."""
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from bot.broker import MT5Broker  # noqa: E402
from bot.config import Config  # noqa: E402
from bot.engine import Engine  # noqa: E402
from bot.fake_mt5 import FakeMT5  # noqa: E402
from bot.journal import Journal  # noqa: E402

UTC = timezone.utc


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=UTC)


def make_bars(start: str, end: str, price: float = 150.0, spread: float = 0.010, weekend: bool = True,
              gaps: tuple = ()) -> pd.DataFrame:
    """Flat minute bars (naive UTC index). The FX week runs Sunday 21:05 -> Friday 21:00 UTC."""
    idx = pd.date_range(start, end, freq="1min")
    keep = np.ones(len(idx), bool)
    if weekend:
        wd, mins = idx.weekday, idx.hour * 60 + idx.minute
        keep &= ~((wd == 4) & (mins >= 21 * 60)) & (wd != 5) & ~((wd == 6) & (mins < 21 * 60 + 5))
    for a, b in gaps:
        keep &= ~((idx >= pd.Timestamp(a)) & (idx < pd.Timestamp(b)))
    idx = idx[keep]
    bid = np.full(len(idx), float(price))
    return pd.DataFrame({"bopen": bid, "bhigh": bid, "blow": bid, "bclose": bid, "aopen": bid + spread,
                         "ahigh": bid + spread, "alow": bid + spread, "aclose": bid + spread}, index=idx)


def set_price(bars: pd.DataFrame, start: str, end: str, bid: float, spread: float = 0.010) -> None:
    m = (bars.index >= pd.Timestamp(start)) & (bars.index < pd.Timestamp(end))
    for c in ("bopen", "bhigh", "blow", "bclose"):
        bars.loc[m, c] = bid
    for c in ("aopen", "ahigh", "alow", "aclose"):
        bars.loc[m, c] = bid + spread


def set_spread(bars: pd.DataFrame, start: str, end: str, spread: float) -> None:
    m = (bars.index >= pd.Timestamp(start)) & (bars.index < pd.Timestamp(end))
    for b, a in (("bopen", "aopen"), ("bhigh", "ahigh"), ("blow", "alow"), ("bclose", "aclose")):
        bars.loc[m, a] = bars.loc[m, b] + spread


def dip(bars: pd.DataFrame, when: str, low: float) -> None:
    bars.loc[pd.Timestamp(when), "blow"] = low


TEST_CFG = replace(Config(), risk_pct=10.0, symbols=("USDJPYm",))


class Rig:
    """A simulator + engine pair with a stepping helper."""

    def __init__(self, bars, state_dir, cfg=TEST_CFG, start: str | None = None, **fake_kw):
        self.cfg = cfg
        self.fake = FakeMT5(bars, 1.17, **fake_kw)
        self.state_dir = state_dir
        self.engine = None
        if start:
            self.start(start)

    def start(self, when: str, dry_run=False, allow_live_flag=False):
        now = utc(when) if isinstance(when, str) else when
        self.fake.set_time(now)
        self.engine = Engine(self.cfg, MT5Broker(self.fake), Journal(self.state_dir, durable=False),
                             dry_run=dry_run, allow_live_flag=allow_live_flag)
        self.engine.startup(now)
        return self.engine

    def run(self, start: str, end: str, every_sec: int = 60):
        t, stop = utc(start), utc(end)
        while t <= stop:
            self.fake.set_time(t)
            self.engine.step(t)
            t += timedelta(seconds=every_sec)

    @property
    def journal(self):
        return self.engine.journal

    def opens(self):
        return [r for r in self.fake.requests if not r.get("position")]

    def closes(self):
        return [r for r in self.fake.requests if r.get("position")]


@pytest.fixture
def week():
    """Mon 12 Oct -> Fri 16 Oct 2026 (gotobi Thu 15 Oct; Fri 9 Oct was the moved Sat-10 gotobi)."""
    return make_bars("2026-10-11 21:05", "2026-10-16 20:59")
