"""24/7 soak tests of the real entry point, bot.main.main(), on the MT5 simulator.

The simulator stands in for the MetaTrader5 module and sleep() advances a virtual clock, so months of real
Exness prices run in minutes, through the same loop, reconnect logic, clock correction and restarts as the live
bot. The PC clock is 0.8 s slow and is corrected by the (simulated) time servers.

test_main_survives_errors_outside_the_trading_step: an exception from poll_interval / quiet / the clock check
must not kill the loop (a dead loop at 00:54:59 misses the post-fix short).
test_main_does_not_trade_on_a_pc_clock_an_hour_out: with the time servers unreachable, a PC clock one hour out
must not pass for a broker in another time zone (it used to buy an hour early).
test_main_starts_on_a_damaged_state_file: a bad state.json (disk fault, a typo when clearing the kill switch)
must not stop the bot from starting and managing its trade.

test_main_hosted_only_around_each_trade: a host that starts the bot only before the buy and before the close
(.github/workflows/host.yml, with --until) must see it stop by itself each time and still close and short on time.

test_main_runs_24_7_with_faults (slow): ~5.5 months, with faults injected the whole time:
  - terminal disconnects of 1-20 min, some exactly at an entry, an exit or the fix second;
  - positions_get failures, requoted and timed-out orders;
  - unexpected exceptions in the trading step and in the housekeeping around it;
  - time servers failing;
  - the whole process killed and restarted (as run_bot.bat does), including in the middle of trades.
It checks:
  - main() never dies on its own and every sleep is sane;
  - never more than one position; nothing left open past its exit except during a fault;
  - no duplicate trade;
  - the trades match a fault-free run of the same loop, except where a fault hit that trade's entry or exit.
"""
from __future__ import annotations

import gc
import logging
import os
import random
import sys
import time as real_time
import types
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(os.environ.get("GOTOBI_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(ROOT))

import bot.main as bm  # noqa: E402
from bot.clock import Clock  # noqa: E402
from bot.engine import Engine  # noqa: E402
from bot.fake_mt5 import FakeMT5  # noqa: E402
from bot.gotobi_calendar import GotobiCalendar  # noqa: E402
from bot.journal import Journal  # noqa: E402

UTC = timezone.utc
PC_SLOW = 0.8                      # the PC clock runs this many seconds behind true time
DATA = ROOT / "data"
COLS = ["bopen", "bhigh", "blow", "bclose", "aopen", "ahigh", "alow", "aclose"]
ORIG = {"step": Engine.step, "poll": Engine.poll_interval, "quiet": Engine.quiet, "clock": Clock.maybe_refresh,
        "setup": bm.setup_logging}


class Restart(BaseException):
    """The bot process is killed (power cut, crash); run_bot.bat starts it again 30 s later."""


@dataclass
class Faults:
    disconnects: list[tuple[datetime, datetime]] = field(default_factory=list)
    positions_fail: list[datetime] = field(default_factory=list)
    rejects: list[tuple[datetime, str, int]] = field(default_factory=list)      # (when, open|close, retcode)
    errors: list[tuple[datetime, str]] = field(default_factory=list)           # (when, step|poll|quiet|clock)
    restarts: list[datetime] = field(default_factory=list)
    server_fail_rate: float = 0.0

    def hit(self, a: datetime, b: datetime) -> bool:
        """Was any fault active or injected within [a, b]?"""
        if any(s <= b and e >= a for s, e in self.disconnects):
            return True
        pts = self.positions_fail + [w for w, _, _ in self.rejects] + [w for w, _ in self.errors] + self.restarts
        return any(a <= t <= b for t in pts)


class Sim:
    """Virtual time, the fault schedule, and the checks made at every sleep."""

    def __init__(self, fake: FakeMT5, start: datetime, end: datetime, faults: Faults, seed: int,
                 pc_slow: float = PC_SLOW):
        self.fake, self.true, self.end, self.f = fake, start, end, faults
        self.start, self.pc_slow = start, pc_slow
        self.rng = random.Random(seed)
        self.sleeps = 0
        self.kills = 0
        self.max_positions = 0
        self.errors = {k: sorted(w for w, kind in faults.errors if kind == k) for k in ("step", "poll", "quiet", "clock")}
        ev = [(a, "down", None) for a, _ in faults.disconnects] + [(b, "up", None) for _, b in faults.disconnects]
        ev += [(t, "posfail", None) for t in faults.positions_fail] + [(t, "restart", None) for t in faults.restarts]
        ev += [(t, "reject", (k, rc)) for t, k, rc in faults.rejects]
        self.events = sorted(ev, key=lambda e: e[0])
        self.ei = 0
        fake.set_time(start)

    def wall(self) -> float:                        # the PC clock the bot reads
        return self.true.timestamp() - self.pc_slow

    def mono(self) -> float:                        # the monotonic counter: real elapsed time, never reset
        return (self.true - self.start).total_seconds()

    def query(self, host: str):                     # one SNTP answer
        if self.rng.random() < self.f.server_fail_rate:
            raise OSError("timed out")
        # exact, no jitter: the simulator prices an order at the open of the minute it lands in, so a few ms of
        # clock difference at 00:53:59.99 vs 00:54:00.00 would swap a whole minute's price between two runs
        return self.pc_slow, 0.04

    def advance(self, sec: float, allow_restart: bool = True) -> None:
        new = self.true + timedelta(seconds=sec)
        while self.ei < len(self.events) and self.events[self.ei][0] <= new:
            when, kind, arg = self.events[self.ei]
            self.ei += 1
            if kind == "down":
                self.fake.connected = False
            elif kind == "up":
                self.fake.connected = not any(s <= when < e for s, e in self.f.disconnects)
            elif kind == "posfail":
                self.fake.positions_fail = 3
            elif kind == "reject":
                self.fake.fail_next(arg[0], arg[1], times=2)
            elif kind == "restart" and allow_restart:
                self.true = when
                self.fake.set_time(when)
                self.kills += 1
                raise Restart(when)
        self.true = new
        self.fake.set_time(new)
        self.max_positions = max(self.max_positions, len(self.fake.positions))

    def sleep(self, sec: float) -> None:
        assert 0 < sec <= 60.001, f"insane sleep request {sec!r} at {self.true}"
        self.sleeps += 1
        self.advance(sec)
        if self.true >= self.end:
            raise KeyboardInterrupt

    def due(self, kind: str) -> bool:
        q = self.errors[kind]
        if q and q[0] <= self.true:
            q.pop(0)
            return True
        return False


def load_real_bars(start: datetime, end: datetime) -> pd.DataFrame:
    lo, hi = pd.Timestamp(start.replace(tzinfo=None)) - pd.Timedelta(days=4), pd.Timestamp(end.replace(tzinfo=None))
    parts = []
    for f in ("USDJPYm_m1.parquet", "USDJPYm_2026_10_m1.parquet"):
        if (DATA / f).exists():
            parts.append(pd.read_parquet(DATA / f, columns=COLS,
                                         filters=[("Timestamp", ">=", lo), ("Timestamp", "<=", hi)]))
    if not parts:
        pytest.skip("Exness minute data not present (data/ is not in git)")
    df = pd.concat(parts).sort_index()
    return df[~df.index.duplicated()]


def run_main(monkeypatch, tmp: Path, bars: pd.DataFrame, start: datetime, end: datetime, faults: Faults,
             seed: int = 1, poll_sec: float = 30.0, pc_slow: float = PC_SLOW):
    """Run bot.main.main() from start to end the way run_bot.bat does: start it again 30 s after any exit."""
    fake = FakeMT5(bars, 1.17, balance=1000.0, currency="EUR", leverage=500)
    sim = Sim(fake, start, end, faults, seed, pc_slow=pc_slow)
    tmp.mkdir(parents=True, exist_ok=True)
    state = tmp / "state"
    cfg_path = tmp / "bot_config.toml"
    cfg_path.write_text(f'symbols = ["USDJPYm"]\nrisk_pct = 6.0\npoll_sec = {poll_sec}\n'
                        f'state_dir = "{state.as_posix()}"\n', encoding="utf-8")

    def quiet_logging(state_dir):            # keep the log file, drop the console output
        ORIG["setup"](state_dir)
        root = logging.getLogger()
        root.handlers[:] = [h for h in root.handlers if isinstance(h, logging.FileHandler)]

    def step(self, now):
        if sim.due("step"):
            raise RuntimeError("injected fault in step")
        return ORIG["step"](self, now)

    def poll(self, now):
        if sim.due("poll"):
            raise RuntimeError("injected fault in poll_interval")
        return ORIG["poll"](self, now)

    def quiet(self, now):
        if sim.due("quiet"):
            raise RuntimeError("injected fault in quiet")
        return ORIG["quiet"](self, now)

    def refresh(self):
        if sim.due("clock"):
            raise ValueError("injected fault in the clock check")
        return ORIG["clock"](self)

    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    monkeypatch.setattr(bm, "time", types.SimpleNamespace(sleep=sim.sleep, gmtime=real_time.gmtime))
    monkeypatch.setattr(bm, "keep_awake", lambda: None)
    monkeypatch.setattr(bm, "Clock", lambda servers: Clock(servers, query=sim.query, wall=sim.wall, mono=sim.mono))
    monkeypatch.setattr(bm, "setup_logging", quiet_logging)
    monkeypatch.setattr(Engine, "step", step)
    monkeypatch.setattr(Engine, "poll_interval", poll)
    monkeypatch.setattr(Engine, "quiet", quiet)
    monkeypatch.setattr(Clock, "maybe_refresh", refresh)

    saved = logging.getLogger().handlers[:]
    codes = []
    try:
        while True:
            try:
                rc = bm.main(["--config", str(cfg_path)])
            except Restart:
                rc = "killed"
            except KeyboardInterrupt:
                rc = "end"
            if rc == 0 and sim.true >= end:
                rc = "end"
            codes.append(rc)
            if rc == "end":
                break
            assert rc in ("killed", 3), f"main() exited by itself with {rc!r} at {sim.true} (codes {codes})"
            gc.collect()                                  # the dead process lets go of its lock file
            sim.advance(30, allow_restart=False)          # run_bot.bat waits 30 s
            if sim.true >= end:
                break
    finally:
        for h in logging.getLogger().handlers:
            h.close()
        logging.getLogger().handlers[:] = saved
    return Journal(state, durable=False), fake, sim, codes


# --------------------------------------------------------------------------------------------- fast test
def test_main_survives_errors_outside_the_trading_step(monkeypatch, tmp_path):
    """poll_interval, quiet and the clock check run outside the trading step's try/except in main(): if one of
    them raised, the process would die and run_bot.bat would bring it back 30 s later, too late for the
    fix-second sell."""
    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import make_bars
    bars = make_bars("2026-10-11 21:05", "2026-10-16 20:59")
    start, end = datetime(2026, 10, 14, 15, 0, tzinfo=UTC), datetime(2026, 10, 15, 2, 0, tzinfo=UTC)
    f = Faults(errors=[(datetime(2026, 10, 14, 15, 10, tzinfo=UTC), "poll"),
                       (datetime(2026, 10, 14, 18, 0, tzinfo=UTC), "quiet"),
                       (datetime(2026, 10, 14, 19, 0, tzinfo=UTC), "clock"),
                       (datetime(2026, 10, 15, 0, 54, 50, tzinfo=UTC), "poll")])
    journal, fake, sim, codes = run_main(monkeypatch, tmp_path, bars, start, end, f, poll_sec=5.0)
    assert codes == ["end"], f"the loop died: {codes}"
    assert journal.get("2026-10-15")["status"] == "closed"
    short = journal.get("2026-10-15/short")
    assert short is not None and short["status"] == "closed", short
    assert -1.5 <= short["sent_vs_fix_sec"] <= 0.5, short


def test_main_does_not_trade_on_a_pc_clock_an_hour_out(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import make_bars
    bars = make_bars("2026-10-11 21:05", "2026-10-16 20:59")
    start, end = datetime(2026, 10, 14, 14, 40, tzinfo=UTC), datetime(2026, 10, 14, 16, 30, tzinfo=UTC)
    f = Faults(server_fail_rate=1.0)                     # UDP 123 blocked: the clock can never be checked
    journal, fake, sim, codes = run_main(monkeypatch, tmp_path, bars, start, end, f, poll_sec=5.0,
                                         pc_slow=-3600.0)  # the PC clock is an hour ahead
    assert codes == ["end"], codes
    assert not [d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN], "it traded on a clock an hour out"


def test_main_starts_on_a_damaged_state_file(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import make_bars
    bars = make_bars("2026-10-11 21:05", "2026-10-16 20:59")
    start, end = datetime(2026, 10, 14, 15, 0, tzinfo=UTC), datetime(2026, 10, 15, 1, 40, tzinfo=UTC)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "state.json").write_text('{"slots": {"2026-10-1', encoding="utf-8")
    (tmp_path / "state" / "state.json.bak").write_text('{"slots": {}}', encoding="utf-8")
    journal, fake, sim, codes = run_main(monkeypatch, tmp_path, bars, start, end, Faults(), poll_sec=5.0)
    assert codes == ["end"], codes
    assert journal.get("2026-10-15")["status"] == "closed" and journal.get("2026-10-15/short")["status"] == "closed"


def test_main_keeps_running_but_opens_nothing_when_all_state_is_lost(monkeypatch, tmp_path):
    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import make_bars
    bars = make_bars("2026-10-11 21:05", "2026-10-16 20:59")
    start, end = datetime(2026, 10, 14, 15, 0, tzinfo=UTC), datetime(2026, 10, 15, 1, 40, tzinfo=UTC)
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "state.json").write_text("garbage", encoding="utf-8")
    journal, fake, sim, codes = run_main(monkeypatch, tmp_path, bars, start, end, Faults(), poll_sec=5.0)
    assert codes == ["end"], codes                       # it did not crash or loop on restarts
    assert journal.halted and "--clear-halt" in journal.halted["reason"]
    assert not [d for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN]


def test_main_hosted_only_around_each_trade(monkeypatch, tmp_path):
    """The free cloud host (.github/workflows/host.yml) starts the bot on a fresh machine before the 15:55 buy and
    again before the 00:54 close, each time with --until, carrying the state folder over. Each run must stop by
    itself (exit 0) once nothing is due, and the second must close the long on time and trade the short."""
    sys.path.insert(0, str(ROOT / "tests"))
    from conftest import make_bars
    bars = make_bars("2026-10-11 21:05", "2026-10-16 20:59")
    fake = FakeMT5(bars, 1.17, balance=1000.0, currency="EUR", leverage=500)
    sim = Sim(fake, datetime(2026, 10, 14, 14, 13, tzinfo=UTC), datetime(2026, 10, 15, 3, 0, tzinfo=UTC), Faults(), 1)
    state = tmp_path / "state"
    cfg_path = tmp_path / "bot_config.toml"
    cfg_path.write_text(f'symbols = ["USDJPYm"]\nrisk_pct = 6.0\npoll_sec = 5.0\nstate_dir = "{state.as_posix()}"\n',
                        encoding="utf-8")

    def quiet_logging(state_dir):
        ORIG["setup"](state_dir)
        root = logging.getLogger()
        root.handlers[:] = [h for h in root.handlers if isinstance(h, logging.FileHandler)]

    monkeypatch.setitem(sys.modules, "MetaTrader5", fake)
    monkeypatch.setattr(bm, "time", types.SimpleNamespace(sleep=sim.sleep, gmtime=real_time.gmtime))
    monkeypatch.setattr(bm, "keep_awake", lambda: None)
    monkeypatch.setattr(bm, "Clock", lambda servers: Clock(servers, query=sim.query, wall=sim.wall, mono=sim.mono))
    monkeypatch.setattr(bm, "setup_logging", quiet_logging)
    saved = logging.getLogger().handlers[:]
    try:
        assert bm.main(["--config", str(cfg_path), "--until", "2026-10-14T18:00Z"]) == 0
        assert datetime(2026, 10, 14, 18, 0, tzinfo=UTC) <= sim.true < datetime(2026, 10, 14, 18, 1, tzinfo=UTC)
        assert Journal(state, durable=False).get("2026-10-15")["status"] == "open"
        assert len(fake.positions) == 1
        gc.collect()                                     # the finished run lets go of its lock files
        sim.advance((datetime(2026, 10, 14, 22, 43, tzinfo=UTC) - sim.true).total_seconds(), allow_restart=False)
        assert bm.main(["--config", str(cfg_path), "--until", "2026-10-15T01:30Z"]) == 0
        assert sim.true < datetime(2026, 10, 15, 1, 31, tzinfo=UTC)
    finally:
        for h in logging.getLogger().handlers:
            h.close()
        logging.getLogger().handlers[:] = saved
    journal = Journal(state, durable=False)
    long, short = journal.get("2026-10-15"), journal.get("2026-10-15/short")
    assert long["status"] == "closed" and long["closed"].startswith("2026-10-15T00:54"), long
    assert short is not None and short["status"] == "closed", short
    assert not fake.positions


def test_until_must_be_a_time(tmp_path):
    assert bm.main(["--until", "tomorrow"]) == 2
    assert bm.parse_until("2026-10-19T18:00Z") == datetime(2026, 10, 19, 18, 0, tzinfo=UTC)
    assert bm.parse_until("2026-10-19 18:00") == datetime(2026, 10, 19, 18, 0, tzinfo=UTC)


# --------------------------------------------------------------------------------------------- the soak
def make_faults(start: datetime, end: datetime, seed: int) -> Faults:
    rng = random.Random(seed)
    cal = GotobiCalendar()
    slots = [cal.slot(d) for d in cal.trade_days(start.date(), end.date())]
    span = (end - start).total_seconds()

    def anytime():
        return start + timedelta(seconds=rng.uniform(0, span))
    f = Faults(server_fail_rate=0.3)
    for _ in range(15):                                               # random disconnects, 1-20 min
        a = anytime()
        f.disconnects.append((a, a + timedelta(minutes=rng.uniform(1, 20))))
    p = rng.sample(slots, 14)
    for s in p[0:3]:                                                  # down across the long's entry
        f.disconnects.append((s.entry - timedelta(minutes=1), s.entry + timedelta(minutes=rng.uniform(2, 8))))
    for s in p[3:6]:                                                  # ... across the long's exit
        f.disconnects.append((s.exit - timedelta(seconds=30), s.exit + timedelta(seconds=rng.uniform(30, 300))))
    for s in p[6:9]:                                                  # ... across the fix second
        f.disconnects.append((s.short_open - timedelta(seconds=2), s.short_open + timedelta(seconds=rng.uniform(3, 20))))
    for s in p[9:11]:                                                 # ... across the buy-back
        f.disconnects.append((s.short_close - timedelta(minutes=1), s.short_close + timedelta(minutes=3)))
    f.positions_fail = [anytime() for _ in range(12)]
    f.rejects = ([(s.entry - timedelta(seconds=5), "open", 10004) for s in rng.sample(slots, 4)] +    # requotes
                 [(s.exit - timedelta(seconds=5), "close", 10012) for s in rng.sample(slots, 3)])     # timeouts
    f.errors = sorted([(anytime(), "step") for _ in range(25)]
                      + [(s.short_open - timedelta(seconds=0.5), "step") for s in p[11:13]]
                      + [(s.exit - timedelta(seconds=0.5), "step") for s in p[13:14]]
                      + [(anytime(), k) for k in ("poll", "quiet", "clock") for _ in range(4)])
    f.restarts = sorted([anytime() for _ in range(8)]
                        + [s.entry + timedelta(hours=4) for s in rng.sample(slots, 2)]               # long open
                        + [s.short_open + timedelta(minutes=10) for s in rng.sample(slots, 2)])      # short open
    return f


def decision_windows(cal: GotobiCalendar, key: str):
    """When a fault can legitimately change a trade: around its entry and its exit (not while it is held)."""
    s = cal.slot(datetime.fromisoformat(key[:10]).date())
    m = timedelta(minutes=1)
    if key.endswith("/short"):
        return [(s.short_open - m, s.short_late + m), (s.short_close - m, s.short_close + 25 * m)]
    return [(s.entry - m, s.entry + 120 * m), (s.exit - m, s.exit + 25 * m)]


@pytest.mark.slow
def test_main_runs_24_7_with_faults(monkeypatch, tmp_path):
    start, end = datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 10, 16, 21, 0, tzinfo=UTC)
    bars = load_real_bars(start, end)
    clean, _, sim0, codes0 = run_main(monkeypatch, tmp_path / "clean", bars, start, end, Faults())
    assert codes0 == ["end"], f"the fault-free run did not run straight through: {codes0}"
    faults = make_faults(start, end, seed=7)
    j, fake, sim, codes = run_main(monkeypatch, tmp_path / "faults", bars, start, end, faults, seed=7)

    # it kept running: every exit was a deliberate kill, or a failed start while the terminal was down
    assert codes[-1] == "end" and all(c in ("killed", 3) for c in codes[:-1]), codes
    assert codes.count("killed") == sim.kills > 0
    # never long and short at once, never two trades for one slot, nothing left open
    assert sim0.max_positions <= 1 and sim.max_positions <= 1
    assert not fake.positions, f"positions left open at the end: {fake.positions}"
    entries = [d.comment for d in fake.deal_log if d.entry == fake.DEAL_ENTRY_IN]
    assert len(entries) == len(set(entries)), "a gotobi slot was entered twice"

    cal = GotobiCalendar()
    changed, unexplained = [], []
    keys = sorted(set(clean.slots) | set(j.slots))
    for k in keys:
        a, b = clean.slots.get(k, {}), j.slots.get(k, {})
        if (a.get("status"), a.get("entry_price"), a.get("close_price")) == \
           (b.get("status"), b.get("entry_price"), b.get("close_price")):
            continue
        changed.append(k)
        if not any(faults.hit(lo, hi) for lo, hi in decision_windows(cal, k)):
            unexplained.append((k, a, b))
    assert not unexplained, f"trades differ from the fault-free run with no fault at their entry/exit: {unexplained}"
    assert len(changed) <= 0.3 * len(keys), (len(changed), len(keys))

    # timed exits happen on time unless a fault was going on at that moment
    for k, rec in j.closed():
        if rec.get("reason") != "time" or not rec.get("exit_due"):
            continue
        due, closed = datetime.fromisoformat(rec["exit_due"]), datetime.fromisoformat(rec["closed"])
        late = (closed - due).total_seconds()
        if late > 90:
            assert faults.hit(due - timedelta(minutes=1), due + timedelta(minutes=1)), (k, late, rec)
            assert late < 25 * 60, (k, late)
    print(f"\nsoak: {sim.sleeps:,} loop sleeps, {sim.kills} kills, {len(faults.disconnects)} disconnects, "
          f"{len(faults.errors)} injected exceptions; {len(j.closed())} trades vs {len(clean.closed())} fault-free; "
          f"{len(changed)} slots changed by a fault at their entry/exit")
